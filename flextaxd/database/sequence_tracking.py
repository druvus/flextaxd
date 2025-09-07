"""Unified sequence tracking system for genomes and proteins."""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator, Optional, List, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
import hashlib
import os
from datetime import datetime

from .sqlite import SQLiteTaxonomyRepository
from ..core.models import GenomeInfo
from ..core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


@dataclass
class SequenceFileInfo:
    """Information about a sequence file."""
    file_id: Optional[int] = None
    file_path: Path = field(default_factory=Path)
    file_type: str = "genome"  # 'genome', 'protein_taxa', 'protein_global'
    scope: str = "single_taxa"  # 'single_taxa', 'multi_taxa', 'global'
    taxa_count: int = 1
    sequence_count: Optional[int] = None
    file_exists: bool = False
    file_checksum: Optional[str] = None
    file_size: Optional[int] = None
    last_validated: Optional[datetime] = None
    created_date: Optional[datetime] = None


@dataclass
class TaxaFileMapping:
    """Mapping between taxa and sequence files."""
    mapping_id: Optional[int] = None
    tax_id: int = 0
    file_id: int = 0
    sequence_count: Optional[int] = None
    first_sequence_offset: Optional[int] = None
    last_sequence_offset: Optional[int] = None


class UnifiedSequenceTracker:
    """Unified tracking system for genome and protein sequences."""

    def __init__(self, repository: SQLiteTaxonomyRepository):
        """Initialize with existing repository."""
        self.repository = repository
        self._ensure_sequence_tracking_schema()

    def _ensure_sequence_tracking_schema(self) -> None:
        """Ensure the sequence tracking tables exist."""
        conn = self.repository._get_connection()
        
        try:
            # Create sequence_files table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sequence_files (
                    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL UNIQUE,
                    file_type TEXT NOT NULL CHECK (file_type IN ('genome', 'protein_taxa', 'protein_global')),
                    scope TEXT NOT NULL CHECK (scope IN ('single_taxa', 'multi_taxa', 'global')),
                    taxa_count INTEGER DEFAULT 1 CHECK (taxa_count > 0),
                    sequence_count INTEGER CHECK (sequence_count >= 0),
                    file_exists BOOLEAN DEFAULT FALSE,
                    file_checksum TEXT,
                    file_size INTEGER CHECK (file_size >= 0),
                    last_validated TIMESTAMP,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create taxa_file_mapping table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS taxa_file_mapping (
                    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tax_id INTEGER NOT NULL,
                    file_id INTEGER NOT NULL,
                    sequence_count INTEGER CHECK (sequence_count >= 0),
                    first_sequence_offset INTEGER CHECK (first_sequence_offset >= 0),
                    last_sequence_offset INTEGER CHECK (last_sequence_offset >= 0),
                    FOREIGN KEY (tax_id) REFERENCES nodes (tax_id) ON DELETE CASCADE,
                    FOREIGN KEY (file_id) REFERENCES sequence_files (file_id) ON DELETE CASCADE,
                    UNIQUE(tax_id, file_id)
                )
            """)

            # Create proteins table (enhanced from existing genomes table concept)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proteins (
                    protein_id TEXT PRIMARY KEY,
                    tax_id INTEGER NOT NULL,
                    genome_id TEXT,
                    protein_accession TEXT,
                    gene_name TEXT,
                    sequence_length INTEGER CHECK (sequence_length > 0),
                    product TEXT,
                    ec_number TEXT,
                    go_terms TEXT, -- JSON format
                    FOREIGN KEY (tax_id) REFERENCES nodes (tax_id) ON DELETE CASCADE,
                    FOREIGN KEY (genome_id) REFERENCES genomes (genome_id) ON DELETE CASCADE
                )
            """)

            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sequence_files_type ON sequence_files (file_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sequence_files_scope ON sequence_files (scope)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_taxa_mapping_tax ON taxa_file_mapping (tax_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_taxa_mapping_file ON taxa_file_mapping (file_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proteins_tax ON proteins (tax_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proteins_genome ON proteins (genome_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proteins_accession ON proteins (protein_accession)")

            logger.info("Sequence tracking schema initialized")

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to initialize sequence tracking schema: {e}")

    def register_sequence_file(self, file_path: Path, file_type: str, 
                              scope: str, taxa_list: List[int]) -> int:
        """Register a sequence file with taxa mapping.
        
        Args:
            file_path: Path to sequence file
            file_type: 'genome', 'protein_taxa', 'protein_global'
            scope: 'single_taxa', 'multi_taxa', 'global'
            taxa_list: List of taxa IDs in this file
        
        Returns:
            file_id for tracking
        """
        conn = self.repository._get_connection()
        
        # Calculate file info
        file_info = self._analyze_file(file_path)
        
        try:
            with self.repository.transaction():
                # Insert sequence file record
                cursor = conn.execute("""
                    INSERT INTO sequence_files 
                    (file_path, file_type, scope, taxa_count, sequence_count, 
                     file_exists, file_checksum, file_size, last_validated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(file_path), file_type, scope, len(taxa_list),
                    file_info['sequence_count'], file_info['exists'],
                    file_info['checksum'], file_info['size'], datetime.now()
                ))
                
                file_id = cursor.lastrowid
                
                # Create taxa mappings
                for tax_id in taxa_list:
                    conn.execute("""
                        INSERT INTO taxa_file_mapping (tax_id, file_id, sequence_count)
                        VALUES (?, ?, ?)
                    """, (tax_id, file_id, None))  # sequence_count per taxa TBD
                
                logger.info(f"Registered {file_type} file {file_path} for {len(taxa_list)} taxa")
                return file_id

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to register sequence file {file_path}: {e}")

    def _analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze a FASTA file for basic information."""
        info = {
            'exists': file_path.exists(),
            'size': None,
            'checksum': None,
            'sequence_count': None
        }
        
        if not info['exists']:
            return info
            
        try:
            # Get file size
            info['size'] = file_path.stat().st_size
            
            # Calculate checksum and count sequences
            sequence_count = 0
            hasher = hashlib.sha256()
            
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.write(chunk)
                    sequence_count += chunk.count(b'>')
            
            info['checksum'] = hasher.hexdigest()
            info['sequence_count'] = sequence_count
            
        except Exception as e:
            logger.warning(f"Failed to analyze file {file_path}: {e}")
            
        return info

    def get_files_for_taxa(self, tax_id: int) -> List[SequenceFileInfo]:
        """Get all sequence files associated with a taxonomic node."""
        conn = self.repository._get_connection()
        
        try:
            cursor = conn.execute("""
                SELECT sf.*, tfm.sequence_count as taxa_sequence_count
                FROM sequence_files sf
                JOIN taxa_file_mapping tfm ON sf.file_id = tfm.file_id
                WHERE tfm.tax_id = ?
                ORDER BY sf.file_type, sf.file_path
            """, (tax_id,))
            
            files = []
            for row in cursor.fetchall():
                files.append(SequenceFileInfo(
                    file_id=row['file_id'],
                    file_path=Path(row['file_path']),
                    file_type=row['file_type'],
                    scope=row['scope'],
                    taxa_count=row['taxa_count'],
                    sequence_count=row['sequence_count'],
                    file_exists=bool(row['file_exists']),
                    file_checksum=row['file_checksum'],
                    file_size=row['file_size'],
                    last_validated=row['last_validated'],
                    created_date=row['created_date']
                ))
            
            return files
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get files for taxa {tax_id}: {e}")

    def get_all_accessions_for_taxa(self, tax_id: int) -> Dict[str, List[str]]:
        """Get all accessions for a taxonomic node.
        
        Returns:
        {
            'assembly': ['GCF_000005825.2'],
            'nucleotide': ['NC_000913.3', 'NC_000914.1'],  
            'protein': ['WP_000001234.1', 'WP_000002345.1', ...]
        }
        """
        conn = self.repository._get_connection()
        accessions = {
            'assembly': [],
            'nucleotide': [],
            'protein': []
        }
        
        try:
            # Get assembly and nucleotide accessions from genomes
            cursor = conn.execute("""
                SELECT assembly_accession, genome_id FROM genomes WHERE tax_id = ?
            """, (tax_id,))
            
            for row in cursor.fetchall():
                if row['assembly_accession']:
                    accessions['assembly'].append(row['assembly_accession'])
                # For nucleotide accessions, we might need to parse the genome_id
                # or add a separate nucleotide_accession field
                genome_id = row['genome_id']
                if genome_id and (genome_id.startswith('NC_') or 
                                 genome_id.startswith('NZ_') or 
                                 genome_id.startswith('CP_')):
                    accessions['nucleotide'].append(genome_id)

            # Get protein accessions
            cursor = conn.execute("""
                SELECT protein_accession FROM proteins 
                WHERE tax_id = ? AND protein_accession IS NOT NULL
            """, (tax_id,))
            
            accessions['protein'] = [row['protein_accession'] for row in cursor.fetchall()]
            
            return accessions
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get accessions for taxa {tax_id}: {e}")

    def get_genome_size_info(self, tax_id: int) -> Dict[str, Any]:
        """Get genome size information for a taxonomic node."""
        conn = self.repository._get_connection()
        
        try:
            cursor = conn.execute("""
                SELECT assembly_accession, sequence_length, genome_id
                FROM genomes WHERE tax_id = ?
            """, (tax_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'tax_id': tax_id,
                    'genome_size': row['sequence_length'],
                    'assembly_accession': row['assembly_accession'],
                    'genome_id': row['genome_id']
                }
            else:
                return {
                    'tax_id': tax_id,
                    'genome_size': None,
                    'assembly_accession': None,
                    'genome_id': None
                }
                
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get genome size info for taxa {tax_id}: {e}")

    def track_protein_sequences(self, tax_id: int, proteins: List[Dict[str, Any]], 
                               genome_id: Optional[str] = None) -> int:
        """Track protein sequences for a taxonomic node.
        
        Args:
            tax_id: Taxonomic node ID
            proteins: List of protein information dicts
            genome_id: Optional genome ID these proteins come from
            
        Returns:
            Number of proteins tracked
        """
        conn = self.repository._get_connection()
        
        try:
            with self.repository.transaction():
                inserted = 0
                for protein in proteins:
                    conn.execute("""
                        INSERT OR REPLACE INTO proteins 
                        (protein_id, tax_id, genome_id, protein_accession, gene_name,
                         sequence_length, product, ec_number, go_terms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        protein.get('protein_id'),
                        tax_id,
                        genome_id,
                        protein.get('protein_accession'),
                        protein.get('gene_name'),
                        protein.get('sequence_length'),
                        protein.get('product'),
                        protein.get('ec_number'),
                        protein.get('go_terms')  # JSON string
                    ))
                    inserted += 1
                
                logger.info(f"Tracked {inserted} proteins for tax_id {tax_id}")
                return inserted
                
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to track protein sequences for taxa {tax_id}: {e}")