"""MALT MapDB format exporter for createtaxdb compatibility."""

import sqlite3
from typing import Optional, Dict, Any
from pathlib import Path

from .base import FileBasedExporter
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class MALTMapDBExporter(FileBasedExporter):
    """Exporter for MALT MapDB format used by createtaxdb pipeline.
    
    Creates SQLite database compatible with MEGAN6 toolkit.
    Contains 'info' and 'mappings' tables for sequence-to-taxonomy mapping.
    """
    
    @property
    def exporter_name(self) -> str:
        return "malt_mapdb"
    
    @property
    def file_extensions(self) -> list[str]:
        return [".db", ".sqlite", ".sqlite3"]
    
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in MALT MapDB format.
        
        Creates an SQLite database with:
        - info table: metadata about the database
        - mappings table: sequence_id -> taxonomy_id mappings
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)
        
        logger.info(f"Exporting {tree.node_count} nodes to MALT MapDB format: {output_path}")
        
        # Configuration options
        include_genomes = kwargs.get('include_genomes', True)
        db_version = kwargs.get('db_version', '1.0')
        db_type = kwargs.get('db_type', 'taxonomy')
        
        if not include_genomes or tree.genome_count == 0:
            logger.warning("No genome information available for MALT MapDB export")
            # Create empty database
            self._create_empty_database(output_path, db_version, db_type)
            return
        
        # Create MALT MapDB database
        self._create_malt_database(tree, output_path, db_version, db_type)
        
        logger.info(f"MALT MapDB export completed: {output_path}")
    
    def _create_empty_database(self, output_path: Path, db_version: str, db_type: str) -> None:
        """Create empty MALT MapDB database with schema only."""
        try:
            with sqlite3.connect(output_path) as conn:
                self._create_schema(conn)
                self._insert_info(conn, 0, db_version, db_type)
                conn.commit()
        except Exception as e:
            raise ExportError(f"Failed to create empty MALT MapDB: {e}")
    
    def _create_malt_database(self, tree: TaxonomyTree, output_path: Path, 
                             db_version: str, db_type: str) -> None:
        """Create MALT MapDB database with taxonomy mappings."""
        try:
            with sqlite3.connect(output_path) as conn:
                # Create schema
                self._create_schema(conn)
                
                # Count total mappings
                total_mappings = sum(len(tree.get_genomes_for_node(node.tax_id)) for node in tree)
                
                # Insert info record
                self._insert_info(conn, total_mappings, db_version, db_type)
                
                # Insert mappings
                self._insert_mappings(conn, tree)
                
                # Create indices for performance
                self._create_indices(conn)
                
                conn.commit()
                
                logger.info(f"Created MALT MapDB with {total_mappings} mappings")
                
        except Exception as e:
            raise ExportError(f"Failed to create MALT MapDB: {e}")
    
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        """Create MALT MapDB database schema."""
        # Info table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS info (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Mappings table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id TEXT NOT NULL,
                taxonomy_id INTEGER NOT NULL
            )
        ''')
    
    def _insert_info(self, conn: sqlite3.Connection, total_mappings: int, 
                     db_version: str, db_type: str) -> None:
        """Insert metadata into info table."""
        info_data = [
            ('version', db_version),
            ('type', db_type),
            ('total_mappings', str(total_mappings)),
            ('created_by', 'FlexTaxD'),
            ('format', 'MALT MapDB'),
        ]
        
        conn.executemany('INSERT OR REPLACE INTO info (key, value) VALUES (?, ?)', info_data)
    
    def _insert_mappings(self, conn: sqlite3.Connection, tree: TaxonomyTree) -> None:
        """Insert sequence-to-taxonomy mappings."""
        mappings_data = []
        
        for node in tree:
            genomes = tree.get_genomes_for_node(node.tax_id)
            for genome in genomes:
                # Primary mapping with genome ID
                mappings_data.append((genome.genome_id, node.tax_id))
                
                # Additional mapping with assembly accession if different
                if (genome.assembly_accession and 
                    genome.assembly_accession != genome.genome_id):
                    mappings_data.append((genome.assembly_accession, node.tax_id))
        
        if mappings_data:
            conn.executemany(
                'INSERT INTO mappings (sequence_id, taxonomy_id) VALUES (?, ?)', 
                mappings_data
            )
    
    def _create_indices(self, conn: sqlite3.Connection) -> None:
        """Create database indices for performance."""
        # Index on sequence_id for fast lookups
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_mappings_sequence_id 
            ON mappings(sequence_id)
        ''')
        
        # Index on taxonomy_id for reverse lookups
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_mappings_taxonomy_id 
            ON mappings(taxonomy_id)
        ''')
        
        # Composite index for combined queries
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_mappings_seq_tax 
            ON mappings(sequence_id, taxonomy_id)
        ''')
    
    def validate_database(self, output_path: Path) -> Dict[str, Any]:
        """Validate the created MALT MapDB database."""
        try:
            with sqlite3.connect(output_path) as conn:
                # Check if tables exist
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                table_names = [row[0] for row in tables]
                
                if 'info' not in table_names or 'mappings' not in table_names:
                    return {'valid': False, 'error': 'Missing required tables'}
                
                # Check info table
                info_count = conn.execute("SELECT COUNT(*) FROM info").fetchone()[0]
                
                # Check mappings table
                mappings_count = conn.execute("SELECT COUNT(*) FROM mappings").fetchone()[0]
                
                # Check indices
                indices = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
                index_names = [row[0] for row in indices]
                
                return {
                    'valid': True,
                    'tables': table_names,
                    'info_records': info_count,
                    'mappings_count': mappings_count,
                    'indices': index_names
                }
                
        except Exception as e:
            return {'valid': False, 'error': str(e)}