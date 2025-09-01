"""High-performance SQLite database layer optimized for massive taxonomies."""

from __future__ import annotations
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Dict, List, Tuple, Optional, Any, Iterator
import queue
import time
from pathlib import Path
import tempfile
import os

from ..core.models import TaxonomyNode, TaxonomicRank, GenomeInfo
from ..core.exceptions import DatabaseError


class ConnectionPool:
    """Thread-safe SQLite connection pool for high concurrency."""
    
    def __init__(self, db_path: str, max_connections: int = 32):
        """Initialize connection pool."""
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=max_connections)
        self._active_connections = 0
        self._lock = threading.RLock()
        self._closed = False
        
        # Initialize pool with some connections
        for _ in range(min(4, max_connections)):
            self._create_connection()
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create optimized connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        
        # High-performance pragma settings
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=50000")  # 50MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        conn.execute("PRAGMA page_size=4096")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        
        # Enable foreign keys for data integrity
        conn.execute("PRAGMA foreign_keys=ON")
        
        return conn
    
    @contextmanager
    def get_connection(self):
        """Get connection from pool."""
        if self._closed:
            raise DatabaseError("Connection pool is closed")
        
        conn = None
        try:
            # Try to get from pool
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                # Create new connection if under limit
                with self._lock:
                    if self._active_connections < self.max_connections:
                        conn = self._create_connection()
                        self._active_connections += 1
                    else:
                        # Wait for connection to become available
                        conn = self._pool.get(timeout=30)
            
            yield conn
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn and not self._closed:
                try:
                    self._pool.put_nowait(conn)
                except queue.Full:
                    conn.close()
                    with self._lock:
                        self._active_connections -= 1
    
    def close_all(self):
        """Close all connections in pool."""
        self._closed = True
        
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break
        
        with self._lock:
            self._active_connections = 0


class HighPerformanceTaxonomyDatabase:
    """High-performance database interface for massive taxonomy datasets."""
    
    def __init__(self, db_path: str, max_connections: int = 32):
        """Initialize high-performance database."""
        self.db_path = db_path
        self.pool = ConnectionPool(db_path, max_connections)
        self._prepared_statements: Dict[str, str] = {}
        self._stats = {
            'bulk_inserts': 0,
            'bulk_queries': 0,
            'cache_hits': 0,
            'total_queries': 0
        }
        
        # Initialize schema and indexes
        self._initialize_schema()
    
    def _initialize_schema(self):
        """Initialize optimized database schema."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create nodes table with optimal structure
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    tax_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    rank TEXT NOT NULL DEFAULT 'custom',
                    parent_id INTEGER,
                    lineage_path TEXT,  -- Pre-computed lineage for fast queries
                    depth INTEGER DEFAULT 0,  -- Pre-computed depth
                    FOREIGN KEY (parent_id) REFERENCES nodes(tax_id)
                )
            """)
            
            # Create genomes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS genomes (
                    genome_id TEXT PRIMARY KEY,
                    tax_id INTEGER NOT NULL,
                    file_path TEXT,
                    sequence_length INTEGER,
                    sequence_type TEXT,
                    assembly_accession TEXT,
                    description TEXT,
                    source TEXT,
                    FOREIGN KEY (tax_id) REFERENCES nodes(tax_id)
                )
            """)
            
            # Create optimized indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_nodes_parent_id ON nodes(parent_id)",
                "CREATE INDEX IF NOT EXISTS idx_nodes_rank ON nodes(rank)",
                "CREATE INDEX IF NOT EXISTS idx_nodes_name_fts ON nodes(name)",
                "CREATE INDEX IF NOT EXISTS idx_nodes_lineage ON nodes(lineage_path)",
                "CREATE INDEX IF NOT EXISTS idx_nodes_depth ON nodes(depth)",
                "CREATE INDEX IF NOT EXISTS idx_genomes_tax_id ON genomes(tax_id)",
                "CREATE INDEX IF NOT EXISTS idx_genomes_type ON genomes(sequence_type)",
                "CREATE INDEX IF NOT EXISTS idx_genomes_source ON genomes(source)"
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)
            
            # Create materialized views for common queries
            cursor.execute("""
                CREATE VIEW IF NOT EXISTS node_stats AS
                SELECT 
                    rank,
                    COUNT(*) as node_count,
                    AVG(depth) as avg_depth,
                    MAX(depth) as max_depth
                FROM nodes
                GROUP BY rank
            """)
            
            conn.commit()
        
        # Prepare common statements
        self._prepare_statements()
    
    def _prepare_statements(self):
        """Prepare commonly used SQL statements."""
        self._prepared_statements = {
            'get_node': "SELECT tax_id, name, rank, parent_id FROM nodes WHERE tax_id = ?",
            'get_children': "SELECT tax_id FROM nodes WHERE parent_id = ?",
            'get_ancestors': """
                WITH RECURSIVE ancestors(tax_id, parent_id, depth) AS (
                    SELECT tax_id, parent_id, 0 
                    FROM nodes WHERE tax_id = ?
                    UNION ALL
                    SELECT n.tax_id, n.parent_id, a.depth + 1
                    FROM nodes n
                    JOIN ancestors a ON n.tax_id = a.parent_id
                    WHERE a.parent_id IS NOT NULL AND a.depth < 100
                )
                SELECT tax_id FROM ancestors ORDER BY depth DESC
            """,
            'get_descendants': """
                WITH RECURSIVE descendants(tax_id, parent_id, depth) AS (
                    SELECT tax_id, parent_id, 0 
                    FROM nodes WHERE tax_id = ?
                    UNION ALL
                    SELECT n.tax_id, n.parent_id, d.depth + 1
                    FROM nodes n
                    JOIN descendants d ON n.parent_id = d.tax_id
                    WHERE d.depth < ?
                )
                SELECT tax_id FROM descendants WHERE depth > 0
            """,
            'bulk_insert_nodes': """
                INSERT OR REPLACE INTO nodes 
                (tax_id, name, rank, parent_id, lineage_path, depth)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            'bulk_insert_genomes': """
                INSERT OR REPLACE INTO genomes 
                (genome_id, tax_id, file_path, sequence_length, sequence_type, 
                 assembly_accession, description, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
        }
    
    def bulk_insert_nodes(self, nodes: List[TaxonomyNode], 
                          batch_size: int = 10000,
                          compute_lineage: bool = True) -> int:
        """Bulk insert nodes with optimized batching."""
        total_inserted = 0
        
        # Pre-compute lineages and depths if requested
        if compute_lineage:
            nodes = self._precompute_node_metadata(nodes)
        
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Process in batches
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i:i + batch_size]
                
                batch_data = []
                for node in batch:
                    # Get pre-computed metadata or defaults
                    lineage_path = getattr(node, '_lineage_path', '')
                    depth = getattr(node, '_depth', 0)
                    
                    batch_data.append((
                        node.tax_id,
                        node.name,
                        node.rank.value,
                        node.parent_id,
                        lineage_path,
                        depth
                    ))
                
                cursor.executemany(self._prepared_statements['bulk_insert_nodes'], batch_data)
                total_inserted += len(batch)
                
                if total_inserted % 50000 == 0:
                    print(f"Inserted {total_inserted:,} nodes...")
            
            conn.commit()
            self._stats['bulk_inserts'] += total_inserted
        
        return total_inserted
    
    def _precompute_node_metadata(self, nodes: List[TaxonomyNode]) -> List[TaxonomyNode]:
        """Pre-compute lineage paths and depths for nodes."""
        # Build parent-child map
        parent_map = {}
        node_map = {}
        
        for node in nodes:
            node_map[node.tax_id] = node
            if node.parent_id:
                if node.parent_id not in parent_map:
                    parent_map[node.parent_id] = []
                parent_map[node.parent_id].append(node.tax_id)
        
        # Find roots
        roots = [node for node in nodes if node.parent_id is None]
        
        # DFS to compute lineages and depths
        def compute_metadata(node_id: int, lineage: List[str], depth: int):
            node = node_map.get(node_id)
            if not node:
                return
            
            # Set metadata attributes
            node._lineage_path = '|'.join(lineage + [node.name])
            node._depth = depth
            
            # Recurse to children
            for child_id in parent_map.get(node_id, []):
                compute_metadata(child_id, lineage + [node.name], depth + 1)
        
        # Compute for each tree
        for root in roots:
            compute_metadata(root.tax_id, [], 0)
        
        return nodes
    
    def bulk_query_nodes(self, tax_ids: List[int]) -> Dict[int, TaxonomyNode]:
        """Bulk query nodes with optimal batching."""
        results = {}
        batch_size = 1000
        
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            for i in range(0, len(tax_ids), batch_size):
                batch = tax_ids[i:i + batch_size]
                placeholders = ','.join('?' * len(batch))
                
                query = f"""
                    SELECT tax_id, name, rank, parent_id 
                    FROM nodes 
                    WHERE tax_id IN ({placeholders})
                """
                
                cursor.execute(query, batch)
                
                for row in cursor.fetchall():
                    tax_id, name, rank, parent_id = row
                    
                    try:
                        taxonomic_rank = TaxonomicRank(rank)
                    except ValueError:
                        taxonomic_rank = TaxonomicRank.CUSTOM
                    
                    results[tax_id] = TaxonomyNode(
                        tax_id=tax_id,
                        name=name,
                        rank=taxonomic_rank,
                        parent_id=parent_id
                    )
        
        self._stats['bulk_queries'] += len(tax_ids)
        return results
    
    def parallel_bulk_insert_nodes(self, nodes: List[TaxonomyNode],
                                  max_workers: int = 4) -> int:
        """Insert nodes in parallel for maximum throughput."""
        if len(nodes) < 10000:
            # Use regular bulk insert for small datasets
            return self.bulk_insert_nodes(nodes)
        
        # Split nodes into chunks
        chunk_size = len(nodes) // max_workers
        chunks = [nodes[i:i + chunk_size] for i in range(0, len(nodes), chunk_size)]
        
        total_inserted = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._insert_node_chunk, chunk, i)
                for i, chunk in enumerate(chunks)
            ]
            
            for future in as_completed(futures):
                chunk_result = future.result()
                total_inserted += chunk_result
        
        return total_inserted
    
    def _insert_node_chunk(self, nodes: List[TaxonomyNode], chunk_id: int) -> int:
        """Insert a chunk of nodes in a separate thread."""
        # Create temporary database for this chunk
        with tempfile.NamedTemporaryFile(suffix=f"_chunk_{chunk_id}.db", delete=False) as tmp_f:
            tmp_db_path = tmp_f.name
        
        try:
            # Create temporary database
            temp_conn = sqlite3.connect(tmp_db_path)
            temp_conn.execute("PRAGMA journal_mode=MEMORY")
            temp_conn.execute("PRAGMA synchronous=OFF")
            temp_conn.execute("""
                CREATE TABLE nodes (
                    tax_id INTEGER PRIMARY KEY,
                    name TEXT,
                    rank TEXT,
                    parent_id INTEGER
                )
            """)
            
            # Insert into temporary database
            for node in nodes:
                temp_conn.execute(
                    "INSERT INTO nodes VALUES (?, ?, ?, ?)",
                    (node.tax_id, node.name, node.rank.value, node.parent_id)
                )
            temp_conn.commit()
            temp_conn.close()
            
            # Attach and merge into main database
            with self.pool.get_connection() as main_conn:
                main_conn.execute(f"ATTACH '{tmp_db_path}' AS chunk_{chunk_id}")
                main_conn.execute(f"""
                    INSERT OR REPLACE INTO main.nodes (tax_id, name, rank, parent_id)
                    SELECT tax_id, name, rank, parent_id FROM chunk_{chunk_id}.nodes
                """)
                main_conn.execute(f"DETACH chunk_{chunk_id}")
                main_conn.commit()
            
            return len(nodes)
            
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_db_path):
                os.unlink(tmp_db_path)
    
    def get_node_with_lineage(self, tax_id: int) -> Optional[Tuple[TaxonomyNode, List[str]]]:
        """Get node with pre-computed lineage."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT tax_id, name, rank, parent_id, lineage_path
                FROM nodes WHERE tax_id = ?
            """, (tax_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            tax_id, name, rank, parent_id, lineage_path = row
            
            try:
                taxonomic_rank = TaxonomicRank(rank)
            except ValueError:
                taxonomic_rank = TaxonomicRank.CUSTOM
            
            node = TaxonomyNode(
                tax_id=tax_id,
                name=name,
                rank=taxonomic_rank,
                parent_id=parent_id
            )
            
            lineage = lineage_path.split('|') if lineage_path else []
            
            return node, lineage
    
    def fast_lca_query(self, tax_id1: int, tax_id2: int) -> Optional[int]:
        """Fast LCA using pre-computed lineages."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get lineage paths
            cursor.execute("""
                SELECT lineage_path FROM nodes 
                WHERE tax_id IN (?, ?)
                ORDER BY tax_id
            """, (tax_id1, tax_id2))
            
            results = cursor.fetchall()
            if len(results) != 2:
                return None
            
            lineage1 = results[0][0].split('|') if results[0][0] else []
            lineage2 = results[1][0].split('|') if results[1][0] else []
            
            # Find common prefix
            lca_name = None
            for name1, name2 in zip(lineage1, lineage2):
                if name1 == name2:
                    lca_name = name1
                else:
                    break
            
            if lca_name:
                # Find tax_id for LCA
                cursor.execute("SELECT tax_id FROM nodes WHERE name = ? LIMIT 1", (lca_name,))
                result = cursor.fetchone()
                return result[0] if result else None
            
            return None
    
    def get_subtree_statistics(self, root_id: int) -> Dict[str, Any]:
        """Get comprehensive subtree statistics."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Use recursive CTE for subtree stats
            cursor.execute("""
                WITH RECURSIVE subtree(tax_id, parent_id, depth) AS (
                    SELECT tax_id, parent_id, 0 
                    FROM nodes WHERE tax_id = ?
                    UNION ALL
                    SELECT n.tax_id, n.parent_id, s.depth + 1
                    FROM nodes n
                    JOIN subtree s ON n.parent_id = s.tax_id
                    WHERE s.depth < 50
                )
                SELECT 
                    COUNT(*) as node_count,
                    MAX(depth) as max_depth,
                    COUNT(CASE WHEN tax_id NOT IN (SELECT DISTINCT parent_id FROM subtree WHERE parent_id IS NOT NULL) THEN 1 END) as leaf_count
                FROM subtree
            """, (root_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'node_count': result[0],
                    'max_depth': result[1],
                    'leaf_count': result[2]
                }
            
            return {'node_count': 0, 'max_depth': 0, 'leaf_count': 0}
    
    def create_database_backup(self, backup_path: str):
        """Create optimized database backup."""
        with self.pool.get_connection() as conn:
            # Use SQLite backup API for atomic backup
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            backup_conn.close()
    
    def optimize_database(self):
        """Run database optimization commands."""
        with self.pool.get_connection() as conn:
            print("Optimizing database...")
            
            # Analyze tables for query optimizer
            conn.execute("ANALYZE")
            
            # Vacuum to reclaim space and defragment
            conn.execute("VACUUM")
            
            # Update statistics
            conn.execute("PRAGMA optimize")
            
            conn.commit()
            print("Database optimization complete")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database performance statistics."""
        stats = self._stats.copy()
        
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Database size info
            cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            db_size = cursor.fetchone()[0]
            
            # Table counts
            cursor.execute("SELECT COUNT(*) FROM nodes")
            node_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM genomes")
            genome_count = cursor.fetchone()[0]
            
            stats.update({
                'database_size_bytes': db_size,
                'database_size_mb': db_size / 1024 / 1024,
                'node_count': node_count,
                'genome_count': genome_count,
                'active_connections': self.pool._active_connections
            })
        
        return stats
    
    def close(self):
        """Close database and cleanup resources."""
        self.pool.close_all()


def create_high_performance_database(db_path: str, 
                                   max_connections: int = 32) -> HighPerformanceTaxonomyDatabase:
    """Factory function to create high-performance database."""
    return HighPerformanceTaxonomyDatabase(db_path, max_connections)