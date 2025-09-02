"""High-performance parsers for large-scale taxonomy files."""

from __future__ import annotations
import mmap
import os
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Iterator, Dict, List, Tuple, Optional, Any, Protocol, BinaryIO
from pathlib import Path
import tempfile
import queue
import time
import gzip
import bz2
import lzma
from dataclasses import dataclass
import multiprocessing as mp

from ..core.models import TaxonomyNode, TaxonomicRank, GenomeInfo
from ..core.exceptions import ParseError


@dataclass
class ParsedNode:
    """Lightweight parsed node representation."""
    tax_id: int
    name: str
    rank: str
    parent_id: Optional[int]
    lineage: Optional[List[str]] = None


@dataclass 
class ParsedGenome:
    """Lightweight parsed genome representation."""
    genome_id: str
    tax_id: int
    file_path: Optional[str] = None
    sequence_length: Optional[int] = None
    sequence_type: Optional[str] = None
    assembly_accession: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None


class FileChunk:
    """Represents a chunk of a file for parallel processing."""
    
    def __init__(self, file_path: Path, start: int, end: int, chunk_id: int):
        self.file_path = file_path
        self.start = start
        self.end = end
        self.chunk_id = chunk_id
        self.size = end - start


class ParserProtocol(Protocol):
    """Protocol for parsers that can handle file chunks."""
    
    def parse_chunk(self, chunk: FileChunk) -> Iterator[ParsedNode]:
        """Parse a chunk of file and yield nodes."""
        ...


class MemoryMappedFileReader:
    """Memory-mapped file reader for efficient large file processing."""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._file: Optional[BinaryIO] = None
        self._mmap: Optional[mmap.mmap] = None
        self.size = 0
        
    def __enter__(self) -> MemoryMappedFileReader:
        """Context manager entry."""
        self._file = open(self.file_path, 'rb')
        self._mmap = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        self.size = len(self._mmap)
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if self._mmap:
            self._mmap.close()
        if self._file:
            self._file.close()
    
    def find_line_boundaries(self, num_chunks: int) -> List[Tuple[int, int]]:
        """Find line boundaries for splitting file into chunks."""
        if self._mmap is None:
            raise RuntimeError("File not opened - use as context manager")
        
        if num_chunks <= 1:
            return [(0, self.size)]
        
        chunk_size = self.size // num_chunks
        boundaries = [(0, 0)]  # Start with dummy
        
        for i in range(1, num_chunks):
            # Find approximate chunk boundary
            pos = i * chunk_size
            
            # Find next line boundary
            while pos < self.size and self._mmap[pos:pos+1] != b'\\n':
                pos += 1
            pos += 1  # Include the newline
            
            boundaries.append((boundaries[-1][1], pos))
        
        # Last chunk goes to end of file
        boundaries.append((boundaries[-1][1], self.size))
        boundaries = boundaries[1:]  # Remove dummy
        
        return boundaries


class HighPerformanceNCBIParser:
    """High-performance NCBI taxonomy parser with parallel processing."""
    
    def __init__(self, max_workers: Optional[int] = None):
        """Initialize parser."""
        self.max_workers = max_workers or min(32, mp.cpu_count() * 2)
        self._stats = {
            'files_processed': 0,
            'nodes_parsed': 0,
            'parse_time': 0.0,
            'chunks_processed': 0
        }
    
    def parse_nodes_file(self, nodes_file: Path, 
                        use_parallel: bool = True,
                        chunk_size_mb: int = 100) -> Iterator[ParsedNode]:
        """Parse NCBI nodes.dmp file with optional parallel processing."""
        start_time = time.time()
        
        if not use_parallel or os.path.getsize(nodes_file) < chunk_size_mb * 1024 * 1024:
            # Use sequential processing for small files
            yield from self._parse_nodes_sequential(nodes_file)
        else:
            # Use parallel processing for large files
            yield from self._parse_nodes_parallel(nodes_file, chunk_size_mb)
        
        self._stats['parse_time'] += time.time() - start_time
        self._stats['files_processed'] += 1
    
    def _parse_nodes_sequential(self, nodes_file: Path) -> Iterator[ParsedNode]:
        """Sequential parsing of nodes file."""
        open_func = self._get_open_function(nodes_file)
        
        with open_func(nodes_file, 'rt', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                try:
                    node = self._parse_node_line(line.strip())
                    if node:
                        yield node
                        self._stats['nodes_parsed'] += 1
                except Exception as e:
                    # Log error but continue processing
                    print(f"Warning: Failed to parse line {line_num}: {e}")
                    continue
    
    def _parse_nodes_parallel(self, nodes_file: Path, 
                             chunk_size_mb: int) -> Iterator[ParsedNode]:
        """Parallel parsing of nodes file using memory mapping."""
        # Detect file format
        open_func = self._get_open_function(nodes_file)
        
        if nodes_file.suffix in ['.gz', '.bz2', '.xz']:
            # For compressed files, use streaming parallel approach
            yield from self._parse_compressed_parallel(nodes_file, open_func)
        else:
            # For uncompressed files, use memory mapping
            yield from self._parse_mmap_parallel(nodes_file, chunk_size_mb)
    
    def _parse_mmap_parallel(self, nodes_file: Path, 
                            chunk_size_mb: int) -> Iterator[ParsedNode]:
        """Memory-mapped parallel parsing."""
        chunk_size_bytes = chunk_size_mb * 1024 * 1024
        
        with MemoryMappedFileReader(nodes_file) as reader:
            # Calculate number of chunks
            num_chunks = max(1, reader.size // chunk_size_bytes)
            boundaries = reader.find_line_boundaries(min(num_chunks, self.max_workers))
            
            # Create chunks
            chunks = [
                FileChunk(nodes_file, start, end, i)
                for i, (start, end) in enumerate(boundaries)
                if end > start
            ]
            
            print(f"Processing {nodes_file.name} in {len(chunks)} chunks...")
            
            # Process chunks in parallel
            with ThreadPoolExecutor(max_workers=min(len(chunks), self.max_workers)) as executor:
                futures = [
                    executor.submit(self._parse_node_chunk_mmap, chunk)
                    for chunk in chunks
                ]
                
                for future in as_completed(futures):
                    try:
                        chunk_results = future.result()
                        for node in chunk_results:
                            yield node
                    except Exception as e:
                        print(f"Error processing chunk: {e}")
                        continue
            
            self._stats['chunks_processed'] += len(chunks)
    
    def _parse_node_chunk_mmap(self, chunk: FileChunk) -> List[ParsedNode]:
        """Parse a memory-mapped chunk of the nodes file."""
        results = []
        
        with open(chunk.file_path, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                # Read chunk data
                chunk_data = mm[chunk.start:chunk.end]
                
                # Decode and split into lines
                try:
                    text_data = chunk_data.decode('utf-8')
                except UnicodeDecodeError:
                    text_data = chunk_data.decode('utf-8', errors='ignore')
                
                lines = text_data.split('\\n')
                
                # Process lines
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        node = self._parse_node_line(line)
                        if node:
                            results.append(node)
                    except Exception:
                        # Skip problematic lines
                        continue
        
        self._stats['nodes_parsed'] += len(results)
        return results
    
    def _parse_compressed_parallel(self, file_path: Path, 
                                  open_func: Any) -> Iterator[ParsedNode]:
        """Parallel parsing of compressed files using buffered approach."""
        buffer_size = 1024 * 1024  # 1MB buffer
        line_queue: queue.Queue[Any] = queue.Queue(maxsize=10000)
        
        def reader_thread() -> None:
            """Thread to read lines from compressed file."""
            try:
                with open_func(file_path, 'rt', encoding='utf-8') as f:
                    buffer = []
                    for line in f:
                        buffer.append(line.strip())
                        if len(buffer) >= 1000:  # Process in batches
                            line_queue.put(buffer)
                            buffer = []
                    
                    if buffer:
                        line_queue.put(buffer)
                
                line_queue.put(None)  # Signal end
                
            except Exception as e:
                line_queue.put(e)
        
        # Start reader thread
        reader = threading.Thread(target=reader_thread)
        reader.start()
        
        # Process lines with workers
        with ThreadPoolExecutor(max_workers=self.max_workers // 2) as executor:
            while True:
                item = line_queue.get()
                
                if item is None:  # End signal
                    break
                elif isinstance(item, Exception):
                    raise item
                
                # Submit batch for processing
                future = executor.submit(self._process_line_batch, item)
                
                try:
                    batch_results = future.result()
                    for node in batch_results:
                        yield node
                except Exception as e:
                    print(f"Error processing batch: {e}")
                    continue
        
        reader.join()
    
    def _process_line_batch(self, lines: List[str]) -> List[ParsedNode]:
        """Process a batch of lines."""
        results = []
        
        for line in lines:
            if not line:
                continue
            try:
                node = self._parse_node_line(line)
                if node:
                    results.append(node)
            except Exception:
                continue
        
        self._stats['nodes_parsed'] += len(results)
        return results
    
    def _parse_node_line(self, line: str) -> Optional[ParsedNode]:
        """Parse a single node line from NCBI format."""
        if not line or line.startswith('#'):
            return None
        
        # NCBI nodes.dmp format: tax_id | parent_tax_id | rank | embl_code | division_id | inherited_div_flag | genetic_code_id | ...
        parts = [part.strip() for part in line.split('|')]
        
        if len(parts) < 3:
            return None
        
        try:
            tax_id = int(parts[0])
            parent_id = int(parts[1]) if parts[1] != parts[0] else None  # Handle root
            rank = parts[2].strip()
            
            return ParsedNode(
                tax_id=tax_id,
                name='',  # Will be filled from names file
                rank=rank,
                parent_id=parent_id
            )
            
        except (ValueError, IndexError):
            return None
    
    def parse_names_file(self, names_file: Path, 
                        name_class: str = 'scientific name') -> Dict[int, str]:
        """Parse NCBI names.dmp file efficiently."""
        names = {}
        open_func = self._get_open_function(names_file)
        
        with open_func(names_file, 'rt', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                    
                # names.dmp format: tax_id | name_txt | unique_name | name_class |
                parts = [part.strip() for part in line.split('|')]
                
                if len(parts) < 4:
                    continue
                
                try:
                    tax_id = int(parts[0])
                    name = parts[1].strip()
                    current_class = parts[3].strip()
                    
                    if current_class == name_class:
                        names[tax_id] = name
                        
                except (ValueError, IndexError):
                    continue
        
        return names
    
    def parse_complete_ncbi_taxonomy(self, nodes_file: Path, 
                                   names_file: Path,
                                   use_parallel: bool = True) -> Iterator[TaxonomyNode]:
        """Parse complete NCBI taxonomy with nodes and names."""
        print(f"Parsing NCBI taxonomy files...")
        start_time = time.time()
        
        # Parse names first (faster, smaller file)
        print("Loading names...")
        names = self.parse_names_file(names_file)
        print(f"Loaded {len(names):,} names")
        
        # Parse nodes with names
        print("Parsing nodes...")
        for parsed_node in self.parse_nodes_file(nodes_file, use_parallel):
            name = names.get(parsed_node.tax_id, f"Unknown_{parsed_node.tax_id}")
            
            try:
                rank = TaxonomicRank(parsed_node.rank) if parsed_node.rank else TaxonomicRank.CUSTOM
            except ValueError:
                rank = TaxonomicRank.CUSTOM
            
            yield TaxonomyNode(
                tax_id=parsed_node.tax_id,
                name=name,
                rank=rank,
                parent_id=parsed_node.parent_id
            )
        
        total_time = time.time() - start_time
        print(f"Parsing complete in {total_time:.2f}s")
        self._stats['parse_time'] = total_time
    
    def _get_open_function(self, file_path: Path) -> Any:
        """Get appropriate open function based on file extension."""
        suffix = file_path.suffix.lower()
        
        if suffix == '.gz':
            return gzip.open
        elif suffix == '.bz2':
            return bz2.open
        elif suffix == '.xz':
            return lzma.open
        else:
            return open
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get parsing statistics."""
        stats = self._stats.copy()
        
        if stats['parse_time'] > 0:
            stats['nodes_per_second'] = stats['nodes_parsed'] / stats['parse_time']
        else:
            stats['nodes_per_second'] = 0
        
        return stats


class HighPerformanceGenomeParser:
    """High-performance genome metadata parser."""
    
    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers or mp.cpu_count()
        self._stats = {'genomes_parsed': 0, 'files_processed': 0}
    
    def parse_genome_assembly_summary(self, summary_file: Path) -> Iterator[ParsedGenome]:
        """Parse NCBI assembly summary file."""
        open_func = self._get_open_function(summary_file)
        
        with open_func(summary_file, 'rt', encoding='utf-8') as f:
            # Skip header lines
            for line in f:
                if line.startswith('#'):
                    continue
                break
            
            # Process data lines
            for line in f:
                if not line.strip():
                    continue
                
                try:
                    genome = self._parse_assembly_summary_line(line.strip())
                    if genome:
                        yield genome
                        self._stats['genomes_parsed'] += 1
                except Exception as e:
                    print(f"Warning: Failed to parse genome line: {e}")
                    continue
        
        self._stats['files_processed'] += 1
    
    def _parse_assembly_summary_line(self, line: str) -> Optional[ParsedGenome]:
        """Parse assembly summary line."""
        parts = line.split('\\t')
        
        if len(parts) < 8:
            return None
        
        try:
            # Assembly summary columns (simplified)
            assembly_accession = parts[0]
            taxid = int(parts[5]) if parts[5].isdigit() else None
            organism_name = parts[7]
            assembly_level = parts[11] if len(parts) > 11 else 'Unknown'
            
            if taxid is None:
                return None
            
            return ParsedGenome(
                genome_id=assembly_accession,
                tax_id=taxid,
                assembly_accession=assembly_accession,
                description=organism_name,
                sequence_type='genome',
                source='NCBI'
            )
            
        except (ValueError, IndexError):
            return None
    
    def _get_open_function(self, file_path: Path) -> Any:
        """Get appropriate open function based on file extension.""" 
        suffix = file_path.suffix.lower()
        
        if suffix == '.gz':
            return gzip.open
        elif suffix == '.bz2':
            return bz2.open
        elif suffix == '.xz':
            return lzma.open
        else:
            return open


class ParallelFileProcessor:
    """Generic parallel file processor for large-scale data."""
    
    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers or mp.cpu_count()
    
    def process_files_parallel(self, file_paths: List[Path], 
                             processor_func: Any,
                             use_processes: bool = False) -> Iterator[Any]:
        """Process multiple files in parallel."""
        ExecutorClass = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        
        with ExecutorClass(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(processor_func, file_path)
                for file_path in file_paths
            ]
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    yield result
                except Exception as e:
                    print(f"Error processing file: {e}")
                    continue
    
    def stream_process_large_file(self, file_path: Path,
                                 line_processor: Any,
                                 batch_size: int = 10000) -> Iterator[Any]:
        """Stream process large file with batched parallel processing."""
        open_func = self._get_open_function(file_path)
        
        with open_func(file_path, 'rt', encoding='utf-8') as f:
            batch = []
            
            for line in f:
                batch.append(line.strip())
                
                if len(batch) >= batch_size:
                    # Process batch
                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        chunk_size = len(batch) // self.max_workers
                        if chunk_size == 0:
                            chunk_size = 1
                        
                        chunks = [
                            batch[i:i + chunk_size]
                            for i in range(0, len(batch), chunk_size)
                        ]
                        
                        futures = [
                            executor.submit(self._process_chunk, chunk, line_processor)
                            for chunk in chunks
                        ]
                        
                        for future in as_completed(futures):
                            try:
                                for result in future.result():
                                    yield result
                            except Exception as e:
                                print(f"Error processing chunk: {e}")
                                continue
                    
                    batch.clear()
            
            # Process remaining batch
            if batch:
                for result in self._process_chunk(batch, line_processor):
                    yield result
    
    def _process_chunk(self, lines: List[str], line_processor: Any) -> List[Any]:
        """Process a chunk of lines."""
        results = []
        
        for line in lines:
            if not line:
                continue
            try:
                result = line_processor(line)
                if result is not None:
                    results.append(result)
            except Exception:
                continue
        
        return results
    
    def _get_open_function(self, file_path: Path) -> Any:
        """Get appropriate open function based on file extension."""
        suffix = file_path.suffix.lower()
        
        if suffix == '.gz':
            return gzip.open
        elif suffix == '.bz2':
            return bz2.open
        elif suffix == '.xz':
            return lzma.open
        else:
            return open


def create_high_performance_ncbi_parser(max_workers: Optional[int] = None) -> HighPerformanceNCBIParser:
    """Factory function for high-performance NCBI parser."""
    return HighPerformanceNCBIParser(max_workers)


def benchmark_parser_performance(parser: HighPerformanceNCBIParser, 
                                test_file: Path,
                                use_parallel: bool = True) -> Dict[str, Any]:
    """Benchmark parser performance."""
    start_time = time.time()
    
    # Count nodes
    node_count = 0
    for _ in parser.parse_nodes_file(test_file, use_parallel):
        node_count += 1
    
    total_time = time.time() - start_time
    
    return {
        'nodes_parsed': node_count,
        'total_time_seconds': total_time,
        'nodes_per_second': node_count / total_time if total_time > 0 else 0,
        'file_size_mb': os.path.getsize(test_file) / 1024 / 1024,
        'use_parallel': use_parallel
    }