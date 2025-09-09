"""Comprehensive file validation utilities for genome data."""

import gzip
import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading

from ..core.exceptions import ValidationError


class ValidationLevel(Enum):
    """Validation severity levels."""
    BASIC = "basic"        # File existence and basic checks
    STANDARD = "standard"  # Format validation and size checks  
    COMPREHENSIVE = "comprehensive"  # Full content validation and consistency


@dataclass
class ValidationResult:
    """Result of file validation."""
    file_path: str
    is_valid: bool
    level: ValidationLevel
    file_exists: bool = False
    is_readable: bool = False
    file_size: int = 0
    format_valid: bool = False
    sequence_count: int = 0
    total_length: int = 0
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property 
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class FileValidator:
    """Comprehensive file validation for genome FASTA files."""
    
    def __init__(self, max_workers: int = 4):
        """Initialize validator with thread pool for parallel validation."""
        self.max_workers = max_workers
        self._lock = threading.Lock()
        self._progress_callback: Optional[callable] = None
        
        # File extensions that we can validate
        self.supported_extensions = {'.fasta', '.fa', '.fna', '.ffn', '.faa', '.fas'}
        self.compressed_extensions = {'.gz', '.bz2'}
    
    def set_progress_callback(self, callback: callable) -> None:
        """Set callback function to report validation progress."""
        self._progress_callback = callback
    
    def validate_file(self, file_path: Path, level: ValidationLevel = ValidationLevel.STANDARD) -> ValidationResult:
        """Validate a single genome file."""
        result = ValidationResult(
            file_path=str(file_path),
            is_valid=False,
            level=level
        )
        
        try:
            # Basic checks
            if not self._check_file_existence(file_path, result):
                return result
                
            if not self._check_file_accessibility(file_path, result):
                return result
                
            self._check_file_size(file_path, result)
            
            # Standard level checks
            if level in [ValidationLevel.STANDARD, ValidationLevel.COMPREHENSIVE]:
                if not self._check_file_format(file_path, result):
                    return result
                    
                self._validate_fasta_structure(file_path, result)
            
            # Comprehensive level checks  
            if level == ValidationLevel.COMPREHENSIVE:
                self._validate_fasta_content(file_path, result)
                self._check_file_integrity(file_path, result)
            
            # Determine overall validity
            result.is_valid = not result.has_errors
            
        except Exception as e:
            result.errors.append(f"Unexpected validation error: {str(e)}")
            result.is_valid = False
            
        return result
    
    def validate_files(self, file_paths: List[Path], level: ValidationLevel = ValidationLevel.STANDARD) -> Dict[str, ValidationResult]:
        """Validate multiple files in parallel."""
        results = {}
        
        if self.max_workers == 1:
            # Serial validation
            for i, file_path in enumerate(file_paths):
                result = self.validate_file(file_path, level)
                results[str(file_path)] = result
                self._report_progress(i + 1, len(file_paths))
        else:
            # Parallel validation
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_path = {
                    executor.submit(self.validate_file, path, level): path 
                    for path in file_paths
                }
                
                completed = 0
                for future in concurrent.futures.as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        result = future.result()
                        results[str(path)] = result
                    except Exception as e:
                        # Create error result for failed validation
                        error_result = ValidationResult(
                            file_path=str(path),
                            is_valid=False,
                            level=level,
                            errors=[f"Validation failed: {str(e)}"]
                        )
                        results[str(path)] = error_result
                    
                    completed += 1
                    self._report_progress(completed, len(file_paths))
        
        return results
    
    def _check_file_existence(self, file_path: Path, result: ValidationResult) -> bool:
        """Check if file exists."""
        result.file_exists = file_path.exists()
        if not result.file_exists:
            result.errors.append("File does not exist")
            return False
        return True
    
    def _check_file_accessibility(self, file_path: Path, result: ValidationResult) -> bool:
        """Check if file is readable."""
        try:
            result.is_readable = os.access(file_path, os.R_OK)
            if not result.is_readable:
                result.errors.append("File is not readable (permission denied)")
                return False
        except Exception as e:
            result.errors.append(f"Cannot check file accessibility: {e}")
            return False
        return True
    
    def _check_file_size(self, file_path: Path, result: ValidationResult) -> None:
        """Check file size."""
        try:
            stat = file_path.stat()
            result.file_size = stat.st_size
            
            if result.file_size == 0:
                result.errors.append("File is empty")
            elif result.file_size < 10:  # Very small files are suspicious
                result.warnings.append("File is very small (< 10 bytes)")
            elif result.file_size > 10 * 1024 * 1024 * 1024:  # > 10GB
                result.warnings.append("File is very large (> 10GB)")
                
        except Exception as e:
            result.errors.append(f"Cannot determine file size: {e}")
    
    def _check_file_format(self, file_path: Path, result: ValidationResult) -> bool:
        """Check if file appears to be in a supported format."""
        # Check extension
        suffixes = file_path.suffixes
        
        # Handle compressed files
        if suffixes and suffixes[-1] in self.compressed_extensions:
            if len(suffixes) < 2:
                result.errors.append("Compressed file missing format extension")
                return False
            check_suffix = suffixes[-2]
        else:
            check_suffix = file_path.suffix
        
        if check_suffix.lower() not in self.supported_extensions:
            result.warnings.append(f"Unsupported file extension: {check_suffix}")
        
        return True
    
    def _validate_fasta_structure(self, file_path: Path, result: ValidationResult) -> None:
        """Validate FASTA file structure and count sequences."""
        try:
            open_func = gzip.open if file_path.suffixes and file_path.suffixes[-1] == '.gz' else open
            
            sequence_count = 0
            total_length = 0
            current_seq_length = 0
            in_sequence = False
            line_count = 0
            
            with open_func(file_path, 'rt', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line_count = line_num
                    line = line.strip()
                    
                    if not line:
                        continue
                        
                    if line.startswith('>'):
                        # Header line
                        if in_sequence:
                            # End previous sequence
                            total_length += current_seq_length
                        
                        sequence_count += 1
                        current_seq_length = 0
                        in_sequence = True
                        
                        # Validate header format
                        if len(line) == 1:  # Just '>'
                            result.errors.append(f"Line {line_num}: Empty sequence header")
                        
                    elif in_sequence:
                        # Sequence line
                        seq_line = line.upper()
                        
                        # Check for valid DNA/protein characters
                        if not all(c in 'ACGTUWSMKRYBDHVN-' for c in seq_line):
                            # Check if it's protein
                            if not all(c in 'ACDEFGHIKLMNPQRSTVWYUOBZX*-' for c in seq_line):
                                result.warnings.append(f"Line {line_num}: Non-standard sequence characters found")
                        
                        current_seq_length += len(seq_line)
                        
                    else:
                        # Sequence data before any header
                        result.errors.append(f"Line {line_num}: Sequence data found before header")
                        break
                    
                    # Stop after checking first 1000 lines for performance
                    if line_num > 1000 and result.level != ValidationLevel.COMPREHENSIVE:
                        break
            
            # Add final sequence length
            if in_sequence:
                total_length += current_seq_length
            
            result.sequence_count = sequence_count
            result.total_length = total_length
            result.format_valid = sequence_count > 0
            
            if sequence_count == 0:
                result.errors.append("No valid sequences found")
            elif total_length == 0:
                result.errors.append("No sequence data found")
            
            # File structure checks
            if line_count > 100000 and result.level != ValidationLevel.COMPREHENSIVE:
                result.warnings.append("Large file - only partial validation performed")
                
        except UnicodeDecodeError:
            result.errors.append("File contains invalid character encoding")
        except Exception as e:
            result.errors.append(f"FASTA structure validation failed: {str(e)}")
    
    def _validate_fasta_content(self, file_path: Path, result: ValidationResult) -> None:
        """Comprehensive validation of FASTA content."""
        try:
            open_func = gzip.open if file_path.suffixes and file_path.suffixes[-1] == '.gz' else open
            
            sequence_ids = set()
            duplicate_ids = []
            
            with open_func(file_path, 'rt', encoding='utf-8') as f:
                current_id = None
                current_length = 0
                
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    if line.startswith('>'):
                        # Validate previous sequence length
                        if current_id and current_length == 0:
                            result.warnings.append(f"Sequence '{current_id}' has no sequence data")
                        
                        # Extract sequence ID
                        header = line[1:].strip()
                        seq_id = header.split()[0] if header else ""
                        
                        if not seq_id:
                            result.errors.append(f"Line {line_num}: Empty sequence ID")
                            continue
                        
                        # Check for duplicates
                        if seq_id in sequence_ids:
                            duplicate_ids.append(seq_id)
                        else:
                            sequence_ids.add(seq_id)
                        
                        current_id = seq_id
                        current_length = 0
                    else:
                        # Sequence line
                        current_length += len(line)
            
            # Report duplicates
            if duplicate_ids:
                result.warnings.append(f"Duplicate sequence IDs found: {', '.join(duplicate_ids[:5])}")
                if len(duplicate_ids) > 5:
                    result.warnings.append(f"... and {len(duplicate_ids) - 5} more duplicates")
                    
        except Exception as e:
            result.errors.append(f"Content validation failed: {str(e)}")
    
    def _check_file_integrity(self, file_path: Path, result: ValidationResult) -> None:
        """Check file integrity using checksums and corruption detection."""
        try:
            # Calculate file checksum
            hash_md5 = hashlib.md5()
            
            open_func = gzip.open if file_path.suffixes and file_path.suffixes[-1] == '.gz' else open
            
            with open_func(file_path, 'rb') as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_md5.update(chunk)
            
            # Store checksum for potential future use
            result.checksum = hash_md5.hexdigest()
            
            # Additional integrity checks could be added here
            # (e.g., checking for common corruption patterns)
            
        except Exception as e:
            result.warnings.append(f"Integrity check failed: {str(e)}")
    
    def _report_progress(self, completed: int, total: int) -> None:
        """Report validation progress."""
        if self._progress_callback:
            try:
                self._progress_callback(completed, total)
            except Exception:
                # Ignore callback errors
                pass
    
    def generate_report(self, results: Dict[str, ValidationResult]) -> Dict[str, Any]:
        """Generate summary report of validation results."""
        total_files = len(results)
        valid_files = sum(1 for r in results.values() if r.is_valid)
        
        # Categorize problems
        missing_files = sum(1 for r in results.values() if not r.file_exists)
        unreadable_files = sum(1 for r in results.values() if r.file_exists and not r.is_readable) 
        format_errors = sum(1 for r in results.values() if r.file_exists and r.is_readable and not r.format_valid)
        
        total_sequences = sum(r.sequence_count for r in results.values())
        total_length = sum(r.total_length for r in results.values())
        
        all_errors = []
        all_warnings = []
        for result in results.values():
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
        
        report = {
            "validation_summary": {
                "total_files": total_files,
                "valid_files": valid_files,
                "invalid_files": total_files - valid_files,
                "validation_rate": valid_files / total_files * 100 if total_files > 0 else 0
            },
            "file_status": {
                "missing": missing_files,
                "unreadable": unreadable_files, 
                "format_errors": format_errors,
                "accessible": total_files - missing_files - unreadable_files
            },
            "sequence_statistics": {
                "total_sequences": total_sequences,
                "total_length": total_length,
                "average_length": total_length / total_sequences if total_sequences > 0 else 0
            },
            "error_count": len(all_errors),
            "warning_count": len(all_warnings),
            "most_common_errors": self._get_common_issues(all_errors),
            "most_common_warnings": self._get_common_issues(all_warnings)
        }
        
        return report
    
    def _get_common_issues(self, issues: List[str], limit: int = 5) -> List[Tuple[str, int]]:
        """Get most common issues from a list."""
        from collections import Counter
        
        # Group similar errors
        issue_counts = Counter()
        for issue in issues:
            # Extract the key part of the error message
            key = issue.split(':')[0] if ':' in issue else issue
            issue_counts[key] += 1
        
        return issue_counts.most_common(limit)