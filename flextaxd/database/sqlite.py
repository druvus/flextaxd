"""SQLite implementation of the taxonomy repository."""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator
from typing import Optional, List, Dict, Any, Iterator
from pathlib import Path

from .repository import TaxonomyRepository
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from ..core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class SQLiteTaxonomyRepository(TaxonomyRepository):
    """SQLite-based implementation of taxonomy repository."""
    
    def __init__(self, database_path: str | Path) -> None:
        """Initialize the SQLite repository."""
        self.database_path = Path(database_path)
        self._connection: Optional[sqlite3.Connection] = None
        
        # Ensure parent directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self.initialize()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection, creating if necessary."""
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(
                    self.database_path,
                    check_same_thread=False,
                    isolation_level=None  # Autocommit mode for regular operations
                )
                self._connection.row_factory = sqlite3.Row  # Enable dict-like access
                
                # Enable foreign key constraints
                self._connection.execute("PRAGMA foreign_keys = ON")
                
            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to connect to database {self.database_path}: {e}")
        
        return self._connection
    
    def initialize(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        
        try:
            # Create nodes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    tax_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    rank TEXT DEFAULT 'custom',
                    parent_id INTEGER,
                    FOREIGN KEY (parent_id) REFERENCES nodes (tax_id)
                        ON DELETE CASCADE,
                    CHECK (tax_id > 0),
                    CHECK (parent_id IS NULL OR parent_id > 0),
                    CHECK (tax_id != parent_id)
                )
            """)
            
            # Create genomes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS genomes (
                    genome_id TEXT PRIMARY KEY,
                    tax_id INTEGER NOT NULL,
                    file_path TEXT,
                    sequence_length INTEGER,
                    sequence_type TEXT,
                    assembly_accession TEXT,
                    description TEXT,
                    source TEXT,
                    FOREIGN KEY (tax_id) REFERENCES nodes (tax_id)
                        ON DELETE CASCADE,
                    CHECK (tax_id > 0)
                )
            """)
            
            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nodes_parent 
                ON nodes (parent_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nodes_rank 
                ON nodes (rank)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_genomes_tax_id 
                ON genomes (tax_id)
            """)
            
            logger.info(f"Database schema initialized at {self.database_path}")
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to initialize database schema: {e}")
    
    def save_tree(self, tree: TaxonomyTree) -> None:
        """Save a complete taxonomy tree to storage."""
        with self.transaction():
            conn = self._get_connection()
            
            try:
                # Clear existing data
                conn.execute("DELETE FROM genomes")
                conn.execute("DELETE FROM nodes")
                
                # Insert nodes in topological order (parents before children)
                nodes_to_insert = self._get_nodes_in_insert_order(tree)
                
                for node in nodes_to_insert:
                    self._insert_node_raw(conn, node)
                
                # Insert genomes
                for genome in tree._genomes.values():
                    self.add_genome(genome)
                
                logger.info(f"Saved tree with {tree.node_count} nodes and {tree.genome_count} genomes")
                
            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to save tree: {e}")
    
    def load_tree(self) -> TaxonomyTree:
        """Load the complete taxonomy tree from storage."""
        conn = self._get_connection()
        tree = TaxonomyTree()
        
        try:
            # Load all nodes first
            cursor = conn.execute("""
                SELECT tax_id, name, rank, parent_id 
                FROM nodes
            """)
            
            # Create node objects
            nodes = []
            node_dict = {}
            for row in cursor:
                rank = TaxonomicRank(row['rank']) if row['rank'] else TaxonomicRank.CUSTOM
                node = TaxonomyNode(
                    tax_id=row['tax_id'],
                    name=row['name'],
                    rank=rank,
                    parent_id=row['parent_id']
                )
                nodes.append(node)
                node_dict[node.tax_id] = node
            
            # Sort nodes topologically: parents before children
            def topological_sort(nodes):
                # Separate roots and non-roots
                roots = [node for node in nodes if node.parent_id is None]
                non_roots = [node for node in nodes if node.parent_id is not None]
                
                # Build adjacency list of children for each parent
                children_map = {}
                for node in non_roots:
                    parent_id = node.parent_id
                    if parent_id not in children_map:
                        children_map[parent_id] = []
                    children_map[parent_id].append(node)
                
                # Perform depth-first traversal to get topological order
                sorted_nodes = []
                visited = set()
                
                def dfs(node):
                    if node.tax_id in visited:
                        return
                    visited.add(node.tax_id)
                    sorted_nodes.append(node)
                    
                    # Process children
                    if node.tax_id in children_map:
                        for child in children_map[node.tax_id]:
                            dfs(child)
                
                # Start with roots
                for root in roots:
                    dfs(root)
                
                # Handle any orphaned nodes (nodes whose parents don't exist)
                for node in nodes:
                    if node.tax_id not in visited:
                        sorted_nodes.append(node)
                        visited.add(node.tax_id)
                
                return sorted_nodes
            
            # Sort nodes and add to tree
            sorted_nodes = topological_sort(nodes)
            for node in sorted_nodes:
                tree.add_node(node)
            
            # Load genomes
            cursor = conn.execute("""
                SELECT genome_id, tax_id, file_path, sequence_length, sequence_type, assembly_accession, description, source
                FROM genomes
            """)
            
            for row in cursor:
                genome = GenomeInfo(
                    genome_id=row['genome_id'],
                    tax_id=row['tax_id'],
                    file_path=row['file_path'],
                    sequence_length=row['sequence_length'],
                    sequence_type=row['sequence_type'],
                    assembly_accession=row['assembly_accession'],
                    description=row['description'],
                    source=row['source']
                )
                tree.add_genome(genome)
            
            logger.info(f"Loaded tree with {tree.node_count} nodes and {tree.genome_count} genomes")
            return tree
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to load tree: {e}")
        except ValueError as e:
            raise DatabaseError(f"Invalid data in database: {e}")
    
    def get_node(self, tax_id: int) -> Optional[TaxonomyNode]:
        """Get a single node by its taxonomic ID."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute(
                "SELECT tax_id, name, rank, parent_id FROM nodes WHERE tax_id = ?",
                (tax_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            rank = TaxonomicRank(row['rank']) if row['rank'] else TaxonomicRank.CUSTOM
            return TaxonomyNode(
                tax_id=row['tax_id'],
                name=row['name'],
                rank=rank,
                parent_id=row['parent_id']
            )
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get node {tax_id}: {e}")
    
    def add_node(self, node: TaxonomyNode) -> None:
        """Add a new node to the repository."""
        conn = self._get_connection()
        
        try:
            self._insert_node_raw(conn, node)
            logger.debug(f"Added node {node.tax_id}: {node.name}")
            
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise DatabaseError(f"Node with ID {node.tax_id} already exists")
            elif "FOREIGN KEY constraint failed" in str(e):
                raise DatabaseError(f"Parent node {node.parent_id} does not exist")
            else:
                raise DatabaseError(f"Database constraint violation: {e}")
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to add node: {e}")
    
    def update_node(self, node: TaxonomyNode) -> None:
        """Update an existing node in the repository."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                UPDATE nodes 
                SET name = ?, rank = ?, parent_id = ? 
                WHERE tax_id = ?
            """, (node.name, node.rank.value, node.parent_id, node.tax_id))
            
            if cursor.rowcount == 0:
                raise DatabaseError(f"Node {node.tax_id} does not exist")
            
            logger.debug(f"Updated node {node.tax_id}: {node.name}")
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to update node: {e}")
    
    def delete_node(self, tax_id: int) -> None:
        """Delete a node from the repository."""
        conn = self._get_connection()
        
        try:
            # Check if node exists
            cursor = conn.execute("SELECT COUNT(*) FROM nodes WHERE tax_id = ?", (tax_id,))
            if cursor.fetchone()[0] == 0:
                raise DatabaseError(f"Node {tax_id} not found")
            
            # Check if node has children
            cursor = conn.execute("SELECT COUNT(*) FROM nodes WHERE parent_id = ?", (tax_id,))
            if cursor.fetchone()[0] > 0:
                raise DatabaseError(f"Cannot delete node {tax_id}: has child nodes")
            
            # Delete the node
            cursor = conn.execute("DELETE FROM nodes WHERE tax_id = ?", (tax_id,))
            
            logger.debug(f"Deleted node {tax_id}")
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to delete node: {e}")
    
    def get_children(self, tax_id: int) -> List[TaxonomyNode]:
        """Get all direct children of a node."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                SELECT tax_id, name, rank, parent_id 
                FROM nodes 
                WHERE parent_id = ?
                ORDER BY name
            """, (tax_id,))
            
            children = []
            for row in cursor:
                rank = TaxonomicRank(row['rank']) if row['rank'] else TaxonomicRank.CUSTOM
                node = TaxonomyNode(
                    tax_id=row['tax_id'],
                    name=row['name'],
                    rank=rank,
                    parent_id=row['parent_id']
                )
                children.append(node)
            
            return children
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get children of node {tax_id}: {e}")
    
    def get_descendants(self, tax_id: int) -> List[TaxonomyNode]:
        """Get all descendants of a node using recursive CTE."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                WITH RECURSIVE descendants(tax_id, name, rank, parent_id, level) AS (
                    SELECT tax_id, name, rank, parent_id, 0
                    FROM nodes
                    WHERE parent_id = ?
                    
                    UNION ALL
                    
                    SELECT n.tax_id, n.name, n.rank, n.parent_id, d.level + 1
                    FROM nodes n
                    INNER JOIN descendants d ON n.parent_id = d.tax_id
                )
                SELECT tax_id, name, rank, parent_id FROM descendants
                ORDER BY level, name
            """, (tax_id,))
            
            descendants = []
            for row in cursor:
                rank = TaxonomicRank(row['rank']) if row['rank'] else TaxonomicRank.CUSTOM
                node = TaxonomyNode(
                    tax_id=row['tax_id'],
                    name=row['name'],
                    rank=rank,
                    parent_id=row['parent_id']
                )
                descendants.append(node)
            
            return descendants
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get descendants of node {tax_id}: {e}")
    
    def get_path_to_root(self, tax_id: int) -> List[TaxonomyNode]:
        """Get the path from a node to the root using recursive CTE."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                WITH RECURSIVE path(tax_id, name, rank, parent_id, level) AS (
                    SELECT tax_id, name, rank, parent_id, 0
                    FROM nodes
                    WHERE tax_id = ?
                    
                    UNION ALL
                    
                    SELECT n.tax_id, n.name, n.rank, n.parent_id, p.level + 1
                    FROM nodes n
                    INNER JOIN path p ON n.tax_id = p.parent_id
                )
                SELECT tax_id, name, rank, parent_id FROM path
                ORDER BY level
            """, (tax_id,))
            
            path = []
            for row in cursor:
                rank = TaxonomicRank(row['rank']) if row['rank'] else TaxonomicRank.CUSTOM
                node = TaxonomyNode(
                    tax_id=row['tax_id'],
                    name=row['name'],
                    rank=rank,
                    parent_id=row['parent_id']
                )
                path.append(node)
            
            return path
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get path to root for node {tax_id}: {e}")
    
    def add_genome(self, genome: GenomeInfo) -> None:
        """Add genome information to the repository."""
        conn = self._get_connection()
        
        try:
            # Check if tax_id exists first to provide better error message
            cursor = conn.execute("SELECT COUNT(*) FROM nodes WHERE tax_id = ?", (genome.tax_id,))
            if cursor.fetchone()[0] == 0:
                raise DatabaseError(f"Taxonomy node {genome.tax_id} not found")
            
            conn.execute("""
                INSERT INTO genomes (genome_id, tax_id, file_path, sequence_length, sequence_type, assembly_accession, description, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                genome.genome_id,
                genome.tax_id,
                genome.file_path,
                genome.sequence_length,
                genome.sequence_type,
                genome.assembly_accession,
                genome.description,
                genome.source
            ))
            
            logger.debug(f"Added genome {genome.genome_id} for tax_id {genome.tax_id}")
            
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise DatabaseError(f"Genome with ID {genome.genome_id} already exists")
            elif "FOREIGN KEY constraint failed" in str(e):
                raise DatabaseError(f"Taxonomic node {genome.tax_id} does not exist")
            else:
                raise DatabaseError(f"Database constraint violation: {e}")
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to add genome: {e}")
    
    def get_genomes_for_node(self, tax_id: int) -> List[GenomeInfo]:
        """Get all genomes associated with a taxonomic node."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                SELECT genome_id, tax_id, file_path, sequence_length, sequence_type, assembly_accession, description, source
                FROM genomes
                WHERE tax_id = ?
                ORDER BY genome_id
            """, (tax_id,))
            
            genomes = []
            for row in cursor:
                genome = GenomeInfo(
                    genome_id=row['genome_id'],
                    tax_id=row['tax_id'],
                    file_path=row['file_path'],
                    sequence_length=row['sequence_length'],
                    sequence_type=row['sequence_type'],
                    assembly_accession=row['assembly_accession'],
                    description=row['description'],
                    source=row['source']
                )
                genomes.append(genome)
            
            return genomes
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get genomes for node {tax_id}: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get repository statistics."""
        conn = self._get_connection()
        
        try:
            stats = {}
            
            # Node count
            cursor = conn.execute("SELECT COUNT(*) FROM nodes")
            stats['node_count'] = cursor.fetchone()[0]
            
            # Genome count
            cursor = conn.execute("SELECT COUNT(*) FROM genomes")
            stats['genome_count'] = cursor.fetchone()[0]
            
            # Rank distribution
            cursor = conn.execute("""
                SELECT rank, COUNT(*) as count 
                FROM nodes 
                GROUP BY rank 
                ORDER BY count DESC
            """)
            rank_dist = cursor.fetchall()
            # Convert string ranks back to enum objects
            stats['rank_distribution'] = {
                TaxonomicRank(rank): count for rank, count in rank_dist
            } if rank_dist else {}
            
            # Root nodes (as list of tax_ids)
            cursor = conn.execute("SELECT tax_id FROM nodes WHERE parent_id IS NULL ORDER BY tax_id")
            stats['root_nodes'] = [row[0] for row in cursor.fetchall()]
            
            # Leaf nodes (nodes with no children, as list of tax_ids)
            cursor = conn.execute("""
                SELECT tax_id FROM nodes n1
                WHERE NOT EXISTS (
                    SELECT 1 FROM nodes n2 WHERE n2.parent_id = n1.tax_id
                )
                ORDER BY tax_id
            """)
            stats['leaf_nodes'] = [row[0] for row in cursor.fetchall()]
            
            return stats
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get statistics: {e}")
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        
        # Start an explicit transaction
        conn.execute("BEGIN")
        
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    
    def validate_schema(self) -> bool:
        """Validate that the database schema is correct."""
        conn = self._get_connection()
        
        try:
            # Check that required tables exist
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('nodes', 'genomes')
            """)
            tables = set(row[0] for row in cursor.fetchall())
            
            if tables != {'nodes', 'genomes'}:
                return False
            
            # Check that required columns exist in nodes table
            cursor = conn.execute("PRAGMA table_info(nodes)")
            node_columns = set(row[1] for row in cursor.fetchall())
            required_node_columns = {'tax_id', 'name', 'rank', 'parent_id'}
            
            if not required_node_columns.issubset(node_columns):
                return False
            
            # Check that required columns exist in genomes table
            cursor = conn.execute("PRAGMA table_info(genomes)")
            genome_columns = set(row[1] for row in cursor.fetchall())
            required_genome_columns = {'genome_id', 'tax_id', 'file_path', 'sequence_length', 'sequence_type', 'assembly_accession', 'description', 'source'}
            
            if not required_genome_columns.issubset(genome_columns):
                return False
            
            # Check foreign key constraints are enabled
            cursor = conn.execute("PRAGMA foreign_keys")
            if cursor.fetchone()[0] != 1:
                return False
            
            return True
            
        except sqlite3.Error:
            return False
    
    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def _insert_node_raw(self, conn: sqlite3.Connection, node: TaxonomyNode) -> None:
        """Insert a node without additional validation."""
        conn.execute("""
            INSERT INTO nodes (tax_id, name, rank, parent_id)
            VALUES (?, ?, ?, ?)
        """, (node.tax_id, node.name, node.rank.value, node.parent_id))
    
    def _get_nodes_in_insert_order(self, tree: TaxonomyTree) -> List[TaxonomyNode]:
        """Get nodes in topological order for safe insertion."""
        result = []
        visited = set()
        
        def visit(node: TaxonomyNode) -> None:
            if node.tax_id in visited:
                return
            
            # First visit parent if it exists
            if node.parent_id is not None:
                parent = tree.get_node(node.parent_id)
                if parent:
                    visit(parent)
            
            result.append(node)
            visited.add(node.tax_id)
        
        # Visit all nodes
        for node in tree:
            visit(node)
        
        return result