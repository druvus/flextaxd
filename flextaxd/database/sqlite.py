"""SQLite implementation of the taxonomy repository."""

import sqlite3
import logging
import time
from contextlib import contextmanager
from typing import Generator
from typing import Optional, List, Dict, Any, Iterator, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import concurrent.futures
import threading

from .repository import TaxonomyRepository
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from ..core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class SQLiteTaxonomyRepository(TaxonomyRepository):
    """SQLite-based implementation of taxonomy repository."""

    def __init__(self, database_path: str | Path, max_workers: int = 4) -> None:
        """Initialize the SQLite repository with parallel processing support."""
        self.database_path = Path(database_path)
        self.max_workers = max_workers
        self._connection: Optional[sqlite3.Connection] = None
        self._connection_lock = threading.RLock()  # For thread safety

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
                    isolation_level=None,  # Autocommit mode for regular operations
                )
                self._connection.row_factory = sqlite3.Row  # Enable dict-like access

                # Performance optimizations for production-scale datasets
                self._optimize_connection(self._connection)

            except sqlite3.Error as e:
                raise DatabaseError(
                    f"Failed to connect to database {self.database_path}: {e}"
                )

        return self._connection

    def _optimize_connection(self, conn: sqlite3.Connection) -> None:
        """Apply performance optimizations for production-scale datasets."""
        # Enable foreign key constraints first
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Performance optimizations for large datasets (1M+ nodes, 100K+ genomes)
        conn.execute("PRAGMA synchronous = NORMAL")          # Balance safety/speed (was FULL)
        conn.execute("PRAGMA cache_size = 10000")            # 10MB cache (was 2MB default)
        conn.execute("PRAGMA temp_store = MEMORY")           # Store temporary data in RAM
        conn.execute("PRAGMA mmap_size = 268435456")         # 256MB memory mapping
        conn.execute("PRAGMA journal_mode = WAL")            # Write-Ahead Logging for concurrency
        conn.execute("PRAGMA optimize")                      # Optimize query planner statistics
        
        # Connection-specific optimizations
        conn.execute("PRAGMA threads = 4")                  # Enable multi-threading
        
        logger.info("Applied production-scale performance optimizations")

    def initialize(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()

        try:
            # Create nodes table
            conn.execute(
                """
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
            """
            )

            # Create genomes table
            conn.execute(
                """
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
            """
            )

            # Create indexes for performance
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nodes_parent 
                ON nodes (parent_id)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nodes_rank 
                ON nodes (rank)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_genomes_tax_id 
                ON genomes (tax_id)
            """
            )

            # Add checksum column to genomes table if it doesn't exist
            self._add_checksum_column_if_missing(conn)

            # Phase 4: Enhanced database schema for accession-based architecture
            self._initialize_enhanced_schema(conn)

            logger.info(f"Database schema initialized at {self.database_path}")

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to initialize database schema: {e}")

    def _initialize_enhanced_schema(self, conn: sqlite3.Connection) -> None:
        """Initialize enhanced schema for Phase 4 accession-based architecture."""
        
        # Enhanced genomes table with comprehensive accession tracking
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS genomes_v2 (
                genome_id TEXT PRIMARY KEY,
                tax_id INTEGER NOT NULL,
                assembly_accession TEXT,           -- GCF_/GCA_ (RefSeq/GenBank)
                nucleotide_accession TEXT,         -- NC_/NZ_/CP_ (chromosome/contig)
                biosample_accession TEXT,          -- SAMN_/SAMD_/SAME_ (sample)
                -- File management
                file_path TEXT NOT NULL,           -- Path to genome FASTA file
                file_exists BOOLEAN DEFAULT FALSE, -- Current file existence status
                file_checksum TEXT,                -- SHA256 for integrity
                file_size INTEGER,
                last_validated TIMESTAMP,          -- Last validation timestamp
                -- Metadata
                sequence_count INTEGER,            -- Number of contigs/chromosomes
                total_length INTEGER,              -- Total genome size in bp
                strain TEXT,
                description TEXT,
                source TEXT,                       -- NCBI/GTDB/SILVA/custom
                download_date TIMESTAMP,
                FOREIGN KEY (tax_id) REFERENCES nodes (tax_id) ON DELETE CASCADE,
                UNIQUE(tax_id)  -- One genome per taxonomic node
            )
            """
        )

        # Protein metadata table (tracks individual proteins but not files)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proteins (
                protein_id TEXT PRIMARY KEY,       -- Unique protein identifier
                tax_id INTEGER NOT NULL,
                genome_id TEXT,                    -- Link to parent genome
                protein_accession TEXT,            -- WP_/YP_/NP_ accession
                gene_name TEXT,                    -- Gene name/locus tag
                -- Protein metadata only (no individual file paths)
                sequence_length INTEGER,           -- Protein length in amino acids
                product TEXT,                      -- Protein product description
                ec_number TEXT,                    -- Enzyme commission number
                go_terms TEXT,                     -- Gene ontology terms (JSON)
                FOREIGN KEY (tax_id) REFERENCES nodes (tax_id) ON DELETE CASCADE,
                FOREIGN KEY (genome_id) REFERENCES genomes_v2 (genome_id) ON DELETE CASCADE
            )
            """
        )

        # Unified sequence files table (handles both single and multi-node files)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sequence_files (
                file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,              -- Path to sequence file
                file_type TEXT NOT NULL,              -- 'genome', 'protein_taxa', 'protein_global'
                scope TEXT NOT NULL,                  -- 'single_taxa', 'multi_taxa', 'global'
                taxa_count INTEGER DEFAULT 1,         -- Number of taxa in file
                sequence_count INTEGER,               -- Total sequences in file
                -- File management
                file_exists BOOLEAN DEFAULT FALSE,
                file_checksum TEXT,
                file_size INTEGER,
                last_validated TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(file_path)
            )
            """
        )

        # Links taxa to their sequence files (many-to-many relationship)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS taxa_file_mapping (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tax_id INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                sequence_count INTEGER,               -- Sequences for this taxa in this file
                -- For tracking what's in each file
                first_sequence_offset INTEGER,       -- Position of first sequence for this taxa
                last_sequence_offset INTEGER,        -- Position of last sequence for this taxa
                FOREIGN KEY (tax_id) REFERENCES nodes (tax_id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES sequence_files (file_id) ON DELETE CASCADE,
                UNIQUE(tax_id, file_id)
            )
            """
        )

        # File tracking table for validation and repair
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_registry (
                file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_type TEXT NOT NULL,          -- 'genome'/'protein_taxa'/'protein_global'
                entity_id TEXT NOT NULL,          -- genome_id or tax_id or 'global'
                tax_id INTEGER,                   -- NULL for global protein db
                -- File status
                expected_path TEXT,                -- Original/expected path
                actual_path TEXT,                  -- Current actual path (if moved)
                file_exists BOOLEAN DEFAULT FALSE,
                accessible BOOLEAN DEFAULT FALSE,
                valid_format BOOLEAN DEFAULT FALSE,
                -- File metadata
                size_bytes INTEGER,
                checksum TEXT,
                last_checked TIMESTAMP,
                -- Issues tracking
                issue_type TEXT,                   -- 'missing'/'moved'/'corrupted'/'inaccessible'
                issue_description TEXT,
                repair_attempted BOOLEAN DEFAULT FALSE,
                repair_date TIMESTAMP
            )
            """
        )

        # Accession mapping table (without SRA)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accession_mappings (
                accession TEXT PRIMARY KEY,
                accession_version TEXT,
                tax_id INTEGER NOT NULL,
                accession_type TEXT,              -- 'assembly'/'nucleotide'/'protein'
                FOREIGN KEY (tax_id) REFERENCES nodes (tax_id) ON DELETE CASCADE
            )
            """
        )

        # Create performance indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proteins_tax_id ON proteins (tax_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proteins_genome_id ON proteins (genome_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_genomes_v2_assembly ON genomes_v2 (assembly_accession)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_registry_issues ON file_registry (issue_type, file_exists)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_accession_type ON accession_mappings (accession_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_taxa_file_mapping_tax_id ON taxa_file_mapping (tax_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_taxa_file_mapping_file_id ON taxa_file_mapping (file_id)")

    def _add_checksum_column_if_missing(self, conn: sqlite3.Connection) -> None:
        """Add file_checksum column to genomes table if it doesn't exist."""
        try:
            # Check if the column already exists by querying table info
            cursor = conn.execute("PRAGMA table_info(genomes)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'file_checksum' not in columns:
                logger.info("Adding file_checksum column to genomes table")
                conn.execute("ALTER TABLE genomes ADD COLUMN file_checksum TEXT")
                logger.info("Successfully added file_checksum column")
            else:
                logger.debug("file_checksum column already exists in genomes table")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to add checksum column: {e}")
            # Don't raise, as this isn't critical for basic functionality

    def save_tree(self, tree: TaxonomyTree) -> None:
        """Save a complete taxonomy tree to storage with optimized batch processing."""
        with self.transaction():
            conn = self._get_connection()

            try:
                # Performance optimization: Disable constraints temporarily for bulk insert
                conn.execute("PRAGMA foreign_keys = OFF")
                
                # Clear existing data
                conn.execute("DELETE FROM genomes")
                conn.execute("DELETE FROM nodes")

                # Optimized batch insert for nodes
                self._batch_insert_nodes(conn, tree)
                
                # Optimized batch insert for genomes  
                self._batch_insert_genomes(conn, tree)
                
                # Re-enable constraints and validate
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA integrity_check")

                logger.info(
                    f"Saved tree with {tree.node_count} nodes and {tree.genome_count} genomes using batch processing"
                )

            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to save tree: {e}")

    def _batch_insert_nodes(self, conn: sqlite3.Connection, tree: TaxonomyTree) -> None:
        """Optimized batch insertion of nodes using executemany."""
        # Get nodes in insertion order (parents before children)
        nodes_to_insert = self._get_nodes_in_insert_order(tree)
        
        # Prepare batch data for executemany (much faster than individual inserts)
        node_data = []
        for node in nodes_to_insert:
            node_data.append((
                node.tax_id,
                node.name,
                node.rank.value if node.rank else TaxonomicRank.CUSTOM.value,
                node.parent_id
            ))
        
        # Batch insert with executemany (10-100x faster than individual inserts)
        conn.executemany(
            "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
            node_data
        )
        
        logger.debug(f"Batch inserted {len(node_data)} nodes")

    def _batch_insert_genomes(self, conn: sqlite3.Connection, tree: TaxonomyTree) -> None:
        """Optimized batch insertion of genomes using executemany."""
        if not tree._genomes:
            return
            
        # Prepare batch data for genomes
        genome_data = []
        for genome in tree._genomes.values():
            genome_data.append((
                genome.genome_id,
                genome.tax_id,
                genome.file_path,
                genome.sequence_length,
                genome.sequence_type,
                genome.assembly_accession,
                genome.description,
                genome.source
            ))
        
        # Batch insert genomes
        conn.executemany(
            """INSERT INTO genomes 
               (genome_id, tax_id, file_path, sequence_length, sequence_type, 
                assembly_accession, description, source) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            genome_data
        )
        
        logger.debug(f"Batch inserted {len(genome_data)} genomes")

    def _batch_insert_nodes_parallel(self, conn: sqlite3.Connection, tree: TaxonomyTree, chunk_size: int = 5000) -> None:
        """Parallel batch insertion of nodes for very large taxonomies."""
        nodes_to_insert = self._get_nodes_in_insert_order(tree)
        
        # Use regular method for smaller datasets
        if len(nodes_to_insert) < 20000 or self.max_workers == 1:
            logger.debug(f"Using sequential batch insert for {len(nodes_to_insert)} nodes")
            return self._batch_insert_nodes(conn, tree)
        
        logger.debug(f"Using parallel batch insert for {len(nodes_to_insert)} nodes with {self.max_workers} workers")
        
        # Split nodes into chunks
        node_chunks = [nodes_to_insert[i:i + chunk_size] 
                      for i in range(0, len(nodes_to_insert), chunk_size)]
        
        # Process chunks in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._insert_node_chunk, chunk, i): i
                for i, chunk in enumerate(node_chunks)
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_idx = future_to_chunk[future]
                try:
                    inserted_count = future.result()
                    logger.debug(f"Inserted node chunk {chunk_idx} with {inserted_count} nodes")
                except Exception as e:
                    logger.error(f"Error inserting node chunk {chunk_idx}: {e}")
                    raise DatabaseError(f"Failed to insert node chunk: {e}")
    
    def _insert_node_chunk(self, nodes: List[TaxonomyNode], chunk_idx: int) -> int:
        """Insert a chunk of nodes using a separate connection."""
        # Create new connection for thread safety
        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = OFF")  # Disable for performance
        
        try:
            # Prepare batch data
            node_data = []
            for node in nodes:
                node_data.append((
                    node.tax_id,
                    node.name,
                    node.rank.value if node.rank else TaxonomicRank.CUSTOM.value,
                    node.parent_id
                ))
            
            # Batch insert this chunk
            conn.executemany(
                "INSERT OR REPLACE INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                node_data
            )
            conn.commit()
            
            return len(node_data)
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to insert node chunk {chunk_idx}: {e}")
        finally:
            conn.close()
    
    def _batch_insert_genomes_parallel(self, conn: sqlite3.Connection, tree: TaxonomyTree, chunk_size: int = 2000) -> None:
        """Parallel batch insertion of genomes for very large datasets."""
        if not tree._genomes:
            return
        
        genomes = list(tree._genomes.values())
        
        # Use regular method for smaller datasets
        if len(genomes) < 10000 or self.max_workers == 1:
            logger.debug(f"Using sequential batch insert for {len(genomes)} genomes")
            return self._batch_insert_genomes(conn, tree)
        
        logger.debug(f"Using parallel batch insert for {len(genomes)} genomes with {self.max_workers} workers")
        
        # Split genomes into chunks
        genome_chunks = [genomes[i:i + chunk_size] 
                        for i in range(0, len(genomes), chunk_size)]
        
        # Process chunks in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._insert_genome_chunk, chunk, i): i
                for i, chunk in enumerate(genome_chunks)
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_idx = future_to_chunk[future]
                try:
                    inserted_count = future.result()
                    logger.debug(f"Inserted genome chunk {chunk_idx} with {inserted_count} genomes")
                except Exception as e:
                    logger.error(f"Error inserting genome chunk {chunk_idx}: {e}")
                    raise DatabaseError(f"Failed to insert genome chunk: {e}")
    
    def _insert_genome_chunk(self, genomes: List[GenomeInfo], chunk_idx: int) -> int:
        """Insert a chunk of genomes using a separate connection."""
        # Create new connection for thread safety
        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = OFF")  # Disable for performance
        
        try:
            # Prepare batch data
            genome_data = []
            for genome in genomes:
                genome_data.append((
                    genome.genome_id,
                    genome.tax_id,
                    genome.file_path,
                    genome.sequence_length,
                    genome.sequence_type,
                    genome.assembly_accession,
                    genome.description,
                    genome.source
                ))
            
            # Batch insert this chunk
            conn.executemany(
                """INSERT OR REPLACE INTO genomes 
                   (genome_id, tax_id, file_path, sequence_length, sequence_type, 
                    assembly_accession, description, source) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                genome_data
            )
            conn.commit()
            
            return len(genome_data)
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to insert genome chunk {chunk_idx}: {e}")
        finally:
            conn.close()

    def save_tree_parallel(self, tree: TaxonomyTree) -> None:
        """Save tree using parallel processing for large taxonomies."""
        with self.transaction() as conn:
            try:
                # Performance optimizations for large datasets
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("PRAGMA synchronous = OFF") 
                conn.execute("PRAGMA journal_mode = MEMORY")
                
                # Clear existing data
                conn.execute("DELETE FROM genomes")
                conn.execute("DELETE FROM nodes")
                
                # Use parallel batch inserts for large datasets
                node_count = tree.node_count
                genome_count = tree.genome_count
                
                if node_count > 20000 or genome_count > 10000:
                    logger.info(f"Using parallel processing for large tree: {node_count} nodes, {genome_count} genomes")
                    self._batch_insert_nodes_parallel(conn, tree)
                    self._batch_insert_genomes_parallel(conn, tree)
                else:
                    logger.info(f"Using sequential processing for tree: {node_count} nodes, {genome_count} genomes")
                    self._batch_insert_nodes(conn, tree)
                    self._batch_insert_genomes(conn, tree)
                
                # Re-enable constraints and validate
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA journal_mode = DELETE")
                
                logger.info(
                    f"Saved tree with {node_count} nodes and {genome_count} genomes"
                )
                
            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to save tree in parallel: {e}")

    def load_tree(self) -> TaxonomyTree:
        """Load the complete taxonomy tree from storage with optimized bulk loading."""
        conn = self._get_connection()
        tree = TaxonomyTree()

        try:
            # Optimized bulk loading with memory-efficient processing
            start_time = time.time()
            
            # Load all nodes with optimized query (use index hints for large datasets)
            cursor = conn.execute(
                """
                SELECT tax_id, name, rank, parent_id 
                FROM nodes 
                ORDER BY parent_id NULLS FIRST, tax_id
            """
            )

            # Optimized node creation with minimal object allocation
            nodes = []
            nodes_loaded = 0
            
            for row in cursor:
                rank = (
                    TaxonomicRank(row["rank"]) if row["rank"] else TaxonomicRank.CUSTOM
                )
                node = TaxonomyNode(
                    tax_id=row["tax_id"],
                    name=row["name"],
                    rank=rank,
                    parent_id=row["parent_id"],
                    description=None  # Description not in nodes table schema
                )
                nodes.append(node)
                nodes_loaded += 1

            # Performance logging for large datasets
            nodes_time = time.time() - start_time
            logger.debug(f"Loaded {nodes_loaded} nodes in {nodes_time:.2f}s")

            # Since nodes are pre-ordered by parent_id NULLS FIRST, minimal topological sorting needed
            def topological_sort(nodes: List[TaxonomyNode]) -> List[TaxonomyNode]:
                # Separate roots and non-roots
                roots = [node for node in nodes if node.parent_id is None]
                non_roots = [node for node in nodes if node.parent_id is not None]

                # Build adjacency list of children for each parent
                children_map: Dict[int, List[TaxonomyNode]] = {}
                for node in non_roots:
                    parent_id = node.parent_id
                    if parent_id is not None:
                        if parent_id not in children_map:
                            children_map[parent_id] = []
                        children_map[parent_id].append(node)

                # Perform depth-first traversal to get topological order
                sorted_nodes = []
                visited = set()

                def dfs(node: TaxonomyNode) -> None:
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
            cursor = conn.execute(
                """
                SELECT genome_id, tax_id, file_path, sequence_length, sequence_type, assembly_accession, description, source
                FROM genomes
            """
            )

            for row in cursor:
                genome = GenomeInfo(
                    genome_id=row["genome_id"],
                    tax_id=row["tax_id"],
                    file_path=row["file_path"],
                    sequence_length=row["sequence_length"],
                    sequence_type=row["sequence_type"],
                    assembly_accession=row["assembly_accession"],
                    description=row["description"],
                    source=row["source"],
                    # Default values for fields not in current database schema
                    nucleotide_accession=None,
                    protein_accession=None,
                    biosample_accession=None,
                    strain=None
                )
                tree.add_genome(genome)

            logger.info(
                f"Loaded tree with {tree.node_count} nodes and {tree.genome_count} genomes"
            )
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
                (tax_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            rank = TaxonomicRank(row["rank"]) if row["rank"] else TaxonomicRank.CUSTOM
            return TaxonomyNode(
                tax_id=row["tax_id"],
                name=row["name"],
                rank=rank,
                parent_id=row["parent_id"],
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
            cursor = conn.execute(
                """
                UPDATE nodes 
                SET name = ?, rank = ?, parent_id = ? 
                WHERE tax_id = ?
            """,
                (node.name, node.rank.value, node.parent_id, node.tax_id),
            )

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
            cursor = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE tax_id = ?", (tax_id,)
            )
            if cursor.fetchone()[0] == 0:
                raise DatabaseError(f"Node {tax_id} not found")

            # Check if node has children
            cursor = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE parent_id = ?", (tax_id,)
            )
            if cursor.fetchone()[0] > 0:
                raise DatabaseError(f"Cannot delete node {tax_id}: has child nodes")

            # Delete the node
            cursor = conn.execute("DELETE FROM nodes WHERE tax_id = ?", (tax_id,))

            logger.debug(f"Deleted node {tax_id}")

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to delete node: {e}")

    def remove_subtree(self, tax_id: int) -> int:
        """Remove a node and all its descendants recursively.
        
        Args:
            tax_id: The ID of the root node to remove
            
        Returns:
            Number of nodes removed
        """
        conn = self._get_connection()
        removed_count = 0
        
        try:
            # Check if node exists
            cursor = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE tax_id = ?", (tax_id,)
            )
            if cursor.fetchone()[0] == 0:
                raise DatabaseError(f"Node {tax_id} not found")
            
            # Get all descendants recursively using a recursive CTE
            # First collect all descendants to avoid foreign key constraint issues
            descendants_query = """
                WITH RECURSIVE descendants(tax_id) AS (
                    SELECT ? as tax_id
                    UNION ALL
                    SELECT n.tax_id
                    FROM nodes n
                    JOIN descendants d ON n.parent_id = d.tax_id
                )
                SELECT tax_id FROM descendants ORDER BY tax_id DESC
            """
            
            cursor = conn.execute(descendants_query, (tax_id,))
            nodes_to_remove = [row[0] for row in cursor.fetchall()]
            
            # Remove nodes in reverse order (children before parents) to avoid constraint issues
            for node_id in nodes_to_remove:
                # Also remove any associated genomes
                conn.execute("DELETE FROM genomes WHERE tax_id = ?", (node_id,))
                # Remove the node
                cursor = conn.execute("DELETE FROM nodes WHERE tax_id = ?", (node_id,))
                if cursor.rowcount > 0:
                    removed_count += 1
            
            logger.debug(f"Removed subtree starting at {tax_id}: {removed_count} nodes")
            return removed_count
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to remove subtree: {e}")

    def get_children(self, tax_id: int) -> List[TaxonomyNode]:
        """Get all direct children of a node."""
        conn = self._get_connection()

        try:
            cursor = conn.execute(
                """
                SELECT tax_id, name, rank, parent_id 
                FROM nodes 
                WHERE parent_id = ?
                ORDER BY name
            """,
                (tax_id,),
            )

            children = []
            for row in cursor:
                rank = (
                    TaxonomicRank(row["rank"]) if row["rank"] else TaxonomicRank.CUSTOM
                )
                node = TaxonomyNode(
                    tax_id=row["tax_id"],
                    name=row["name"],
                    rank=rank,
                    parent_id=row["parent_id"],
                    description=None  # Description not in nodes table schema
                )
                children.append(node)

            return children

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get children of node {tax_id}: {e}")

    def get_descendants(self, tax_id: int) -> List[TaxonomyNode]:
        """Get all descendants of a node using recursive CTE."""
        conn = self._get_connection()

        try:
            cursor = conn.execute(
                """
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
            """,
                (tax_id,),
            )

            descendants = []
            for row in cursor:
                rank = (
                    TaxonomicRank(row["rank"]) if row["rank"] else TaxonomicRank.CUSTOM
                )
                node = TaxonomyNode(
                    tax_id=row["tax_id"],
                    name=row["name"],
                    rank=rank,
                    parent_id=row["parent_id"],
                    description=None  # Description not in nodes table schema
                )
                descendants.append(node)

            return descendants

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get descendants of node {tax_id}: {e}")

    def get_descendants_parallel(self, tax_id: int, max_depth: int = None, chunk_size: int = 1000) -> List[TaxonomyNode]:
        """Get descendants using parallel processing for very large subtrees."""
        conn = self._get_connection()
        
        try:
            # First check the size of the subtree
            cursor = conn.execute(
                """
                WITH RECURSIVE descendants(tax_id, level) AS (
                    SELECT tax_id, 0
                    FROM nodes
                    WHERE parent_id = ?
                    
                    UNION ALL
                    
                    SELECT n.tax_id, d.level + 1
                    FROM nodes n
                    INNER JOIN descendants d ON n.parent_id = d.tax_id
                    WHERE (? IS NULL OR d.level < ?)
                )
                SELECT COUNT(*) FROM descendants
                """,
                (tax_id, max_depth, max_depth),
            )
            
            total_descendants = cursor.fetchone()[0]
            
            # Use regular method for smaller subtrees
            if total_descendants < 5000 or self.max_workers == 1:
                logger.debug(f"Using sequential loading for {total_descendants} descendants")
                return self.get_descendants(tax_id)
            
            logger.debug(f"Using parallel loading for {total_descendants} descendants with {self.max_workers} workers")
            
            # Get direct children first
            cursor = conn.execute(
                "SELECT tax_id FROM nodes WHERE parent_id = ? ORDER BY tax_id",
                (tax_id,)
            )
            direct_children = [row[0] for row in cursor.fetchall()]
            
            # Process children in parallel chunks
            all_descendants = []
            child_chunks = [direct_children[i:i + chunk_size] 
                          for i in range(0, len(direct_children), chunk_size)]
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_chunk = {
                    executor.submit(self._get_descendants_chunk, chunk, max_depth): i
                    for i, chunk in enumerate(child_chunks)
                }
                
                for future in concurrent.futures.as_completed(future_to_chunk):
                    chunk_idx = future_to_chunk[future]
                    try:
                        chunk_descendants = future.result()
                        all_descendants.extend(chunk_descendants)
                        logger.debug(f"Loaded descendant chunk {chunk_idx} with {len(chunk_descendants)} nodes")
                    except Exception as e:
                        logger.error(f"Error loading descendant chunk {chunk_idx}: {e}")
                        raise DatabaseError(f"Failed to load descendant chunk: {e}")
            
            # Sort by level then name for consistent ordering
            all_descendants.sort(key=lambda n: (n.tax_id))
            
            return all_descendants
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get descendants in parallel for tax_id {tax_id}: {e}")

    def _get_descendants_chunk(self, child_tax_ids: List[int], max_depth: int = None) -> List[TaxonomyNode]:
        """Get descendants for a chunk of child tax_ids."""
        # Create new connection for thread safety
        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        try:
            all_descendants = []
            
            for child_tax_id in child_tax_ids:
                # Get descendants for this child
                cursor = conn.execute(
                    """
                    WITH RECURSIVE descendants(tax_id, name, rank, parent_id, level) AS (
                        SELECT tax_id, name, rank, parent_id, 0
                        FROM nodes
                        WHERE tax_id = ?
                        
                        UNION ALL
                        
                        SELECT n.tax_id, n.name, n.rank, n.parent_id, d.level + 1
                        FROM nodes n
                        INNER JOIN descendants d ON n.parent_id = d.tax_id
                        WHERE (? IS NULL OR d.level < ?)
                    )
                    SELECT tax_id, name, rank, parent_id FROM descendants
                    ORDER BY level, name
                    """,
                    (child_tax_id, max_depth, max_depth)
                )
                
                for row in cursor:
                    rank = (
                        TaxonomicRank(row["rank"]) if row["rank"] else TaxonomicRank.CUSTOM
                    )
                    node = TaxonomyNode(
                        tax_id=row["tax_id"],
                        name=row["name"], 
                        rank=rank,
                        parent_id=row["parent_id"],
                        description=None
                    )
                    all_descendants.append(node)
            
            return all_descendants
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to load descendant chunk: {e}")
        finally:
            conn.close()

    def get_path_to_root(self, tax_id: int) -> List[TaxonomyNode]:
        """Get the path from a node to the root using recursive CTE."""
        conn = self._get_connection()

        try:
            cursor = conn.execute(
                """
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
            """,
                (tax_id,),
            )

            path = []
            for row in cursor:
                rank = (
                    TaxonomicRank(row["rank"]) if row["rank"] else TaxonomicRank.CUSTOM
                )
                node = TaxonomyNode(
                    tax_id=row["tax_id"],
                    name=row["name"],
                    rank=rank,
                    parent_id=row["parent_id"],
                    description=None  # Description not in nodes table schema
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
            cursor = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE tax_id = ?", (genome.tax_id,)
            )
            if cursor.fetchone()[0] == 0:
                raise DatabaseError(f"Taxonomy node {genome.tax_id} not found")

            conn.execute(
                """
                INSERT INTO genomes (genome_id, tax_id, file_path, sequence_length, sequence_type, assembly_accession, description, source, file_checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    genome.genome_id,
                    genome.tax_id,
                    genome.file_path,
                    genome.sequence_length,
                    genome.sequence_type,
                    genome.assembly_accession,
                    genome.description,
                    genome.source,
                    getattr(genome, 'file_checksum', None),
                ),
            )

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
            cursor = conn.execute(
                """
                SELECT genome_id, tax_id, file_path, sequence_length, sequence_type, assembly_accession, description, source, file_checksum
                FROM genomes
                WHERE tax_id = ?
                ORDER BY genome_id
            """,
                (tax_id,),
            )

            genomes = []
            for row in cursor:
                genome = GenomeInfo(
                    genome_id=row["genome_id"],
                    tax_id=row["tax_id"],
                    file_path=row["file_path"],
                    sequence_length=row["sequence_length"],
                    sequence_type=row["sequence_type"],
                    assembly_accession=row["assembly_accession"],
                    description=row["description"],
                    source=row["source"],
                    file_checksum=row["file_checksum"],
                    # Default values for fields not in current database schema
                    nucleotide_accession=None,
                    protein_accession=None,
                    biosample_accession=None,
                    strain=None
                )
                genomes.append(genome)

            return genomes

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get genomes for node {tax_id}: {e}")

    def get_all_genomes(self) -> List[GenomeInfo]:
        """Get all genomes in the database."""
        conn = self._get_connection()

        try:
            cursor = conn.execute(
                """
                SELECT genome_id, tax_id, file_path, sequence_length, sequence_type, assembly_accession, description, source
                FROM genomes
                ORDER BY genome_id
            """
            )

            genomes = []
            for row in cursor:
                genome = GenomeInfo(
                    genome_id=row["genome_id"],
                    tax_id=row["tax_id"],
                    file_path=row["file_path"],
                    sequence_length=row["sequence_length"],
                    sequence_type=row["sequence_type"],
                    assembly_accession=row["assembly_accession"],
                    description=row["description"],
                    source=row["source"],
                    # Default values for fields not in current database schema
                    nucleotide_accession=None,
                    protein_accession=None,
                    biosample_accession=None,
                    strain=None
                )
                genomes.append(genome)

            return genomes

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get all genomes: {e}")
    
    def get_all_genomes_parallel(self, chunk_size: int = 1000) -> List[GenomeInfo]:
        """Get all genomes using parallel processing for large datasets."""
        conn = self._get_connection()
        
        try:
            # First, get the total count of genomes
            cursor = conn.execute("SELECT COUNT(*) FROM genomes")
            total_genomes = cursor.fetchone()[0]
            
            if total_genomes < 5000 or self.max_workers == 1:
                # Use regular method for smaller datasets
                logger.debug(f"Using sequential loading for {total_genomes} genomes")
                return self.get_all_genomes()
            
            logger.debug(f"Using parallel loading for {total_genomes} genomes with {self.max_workers} workers")
            
            # Calculate chunks
            chunks = []
            for offset in range(0, total_genomes, chunk_size):
                chunks.append((offset, min(chunk_size, total_genomes - offset)))
            
            all_genomes = []
            
            # Process chunks in parallel
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_chunk = {
                    executor.submit(self._load_genome_chunk, offset, limit): (offset, limit)
                    for offset, limit in chunks
                }
                
                for future in concurrent.futures.as_completed(future_to_chunk):
                    offset, limit = future_to_chunk[future]
                    try:
                        chunk_genomes = future.result()
                        all_genomes.extend(chunk_genomes)
                        logger.debug(f"Loaded chunk at offset {offset} with {len(chunk_genomes)} genomes")
                    except Exception as e:
                        logger.error(f"Error loading genome chunk at offset {offset}: {e}")
                        raise DatabaseError(f"Failed to load genome chunk: {e}")
            
            # Sort by genome_id to maintain consistent ordering
            all_genomes.sort(key=lambda g: g.genome_id)
            
            return all_genomes
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get all genomes in parallel: {e}")
    
    def _load_genome_chunk(self, offset: int, limit: int) -> List[GenomeInfo]:
        """Load a chunk of genomes for parallel processing."""
        # Create a new connection for this thread to avoid conflicts
        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        try:
            cursor = conn.execute(
                """
                SELECT genome_id, tax_id, file_path, sequence_length, sequence_type, 
                       assembly_accession, description, source
                FROM genomes
                ORDER BY genome_id
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            
            genomes = []
            for row in cursor:
                genome = GenomeInfo(
                    genome_id=row["genome_id"],
                    tax_id=row["tax_id"],
                    file_path=row["file_path"],
                    sequence_length=row["sequence_length"],
                    sequence_type=row["sequence_type"],
                    assembly_accession=row["assembly_accession"],
                    description=row["description"],
                    source=row["source"],
                    # Default values for fields not in current database schema
                    nucleotide_accession=None,
                    protein_accession=None,
                    biosample_accession=None,
                    strain=None
                )
                genomes.append(genome)
            
            return genomes
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to load genome chunk: {e}")
        finally:
            conn.close()

    def get_statistics(self, validate_files: bool = True) -> Dict[str, Any]:
        """Get repository statistics with enhanced genome analysis.
        
        Args:
            validate_files: Whether to perform filesystem validation (can be slow for large datasets)
        """
        conn = self._get_connection()

        try:
            stats = {}

            # Use single query for all basic node statistics
            cursor = conn.execute(
                """
                SELECT 
                    (SELECT COUNT(*) FROM nodes) as node_count,
                    (SELECT COUNT(*) FROM genomes) as genome_count,
                    (SELECT COUNT(*) FROM nodes WHERE parent_id IS NULL) as root_count,
                    (SELECT COUNT(*) FROM nodes n1 
                     WHERE NOT EXISTS (SELECT 1 FROM nodes n2 WHERE n2.parent_id = n1.tax_id)) as leaf_count
                """
            )
            result = cursor.fetchone()
            stats["node_count"] = result[0]
            stats["genome_count"] = result[1]  
            stats["root_count"] = result[2]
            stats["leaf_count"] = result[3]

            # Enhanced genome statistics (optimized)
            if stats["genome_count"] > 0:
                stats.update(self._get_detailed_genome_statistics_optimized(conn, validate_files))

            # Rank distribution
            cursor = conn.execute(
                """
                SELECT rank, COUNT(*) as count 
                FROM nodes 
                GROUP BY rank 
                ORDER BY count DESC
            """
            )
            rank_dist = cursor.fetchall()
            # Convert string ranks back to enum objects
            stats["rank_distribution"] = (
                {TaxonomicRank(rank): count for rank, count in rank_dist}
                if rank_dist
                else {}
            )

            # Root nodes (as list of tax_ids) - optimized query
            cursor = conn.execute(
                "SELECT tax_id FROM nodes WHERE parent_id IS NULL ORDER BY tax_id"
            )
            stats["root_nodes"] = [row[0] for row in cursor.fetchall()]

            # Leaf nodes (optimized with LEFT JOIN instead of subquery)
            cursor = conn.execute(
                """
                SELECT n1.tax_id 
                FROM nodes n1
                LEFT JOIN nodes n2 ON n2.parent_id = n1.tax_id
                WHERE n2.tax_id IS NULL
                ORDER BY n1.tax_id
            """
            )
            stats["leaf_nodes"] = [row[0] for row in cursor.fetchall()]

            return stats

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get statistics: {e}")

    def _get_detailed_genome_statistics(self, conn: sqlite3.Connection, validate_files: bool) -> Dict[str, Any]:
        """Get detailed genome statistics including file validation and breakdowns."""
        from pathlib import Path
        
        genome_stats = {}
        
        # Get all genome data for analysis
        cursor = conn.execute(
            """
            SELECT genome_id, file_path, sequence_length, sequence_type, source 
            FROM genomes
            """
        )
        genomes = cursor.fetchall()
        
        # File path analysis
        genomes_with_files = 0
        genomes_metadata_only = 0
        file_validation = {"accessible": 0, "missing": 0, "invalid": 0}
        
        # Size analysis
        sequence_lengths = []
        
        # Type and source breakdowns
        sequence_types = {}
        sources = {}
        
        for genome_id, file_path, seq_length, seq_type, source in genomes:
            # File path analysis
            has_file_path = file_path and file_path.strip()
            
            if has_file_path:
                genomes_with_files += 1
                
                # File validation (if requested)
                if validate_files:
                    try:
                        path = Path(file_path)
                        if path.exists():
                            if path.is_file() and path.stat().st_size > 0:
                                file_validation["accessible"] += 1
                            else:
                                file_validation["invalid"] += 1
                        else:
                            file_validation["missing"] += 1
                    except (OSError, PermissionError):
                        file_validation["invalid"] += 1
            else:
                genomes_metadata_only += 1
            
            # Sequence length analysis
            if seq_length is not None and seq_length > 0:
                sequence_lengths.append(seq_length)
            
            # Sequence type breakdown
            type_key = seq_type or "unknown"
            sequence_types[type_key] = sequence_types.get(type_key, 0) + 1
            
            # Source breakdown  
            source_key = source or "unknown"
            sources[source_key] = sources.get(source_key, 0) + 1
        
        # Compile results
        genome_stats["genomes_with_files"] = genomes_with_files
        genome_stats["genomes_metadata_only"] = genomes_metadata_only
        
        if validate_files:
            genome_stats["genome_file_validation"] = file_validation
        
        # Genome size distribution
        if sequence_lengths:
            genome_stats["genome_size_distribution"] = {
                "count": len(sequence_lengths),
                "min": min(sequence_lengths),
                "max": max(sequence_lengths),
                "avg": sum(sequence_lengths) / len(sequence_lengths),
                "median": sorted(sequence_lengths)[len(sequence_lengths) // 2]
            }
        else:
            genome_stats["genome_size_distribution"] = {
                "count": 0,
                "min": 0,
                "max": 0,
                "avg": 0.0,
                "median": 0
            }
        
        # Breakdowns
        genome_stats["sequence_type_breakdown"] = sequence_types
        genome_stats["source_distribution"] = sources
        
        return genome_stats

    def _get_detailed_genome_statistics_optimized(self, conn: sqlite3.Connection, validate_files: bool) -> Dict[str, Any]:
        """Get detailed genome statistics with optimized queries and batched file validation."""
        import os
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import statistics
        
        genome_stats = {}
        
        # Get overall statistics first
        cursor = conn.execute(
            """
            SELECT 
                COUNT(CASE WHEN file_path IS NOT NULL AND file_path != '' THEN 1 END) as genomes_with_files,
                COUNT(CASE WHEN file_path IS NULL OR file_path = '' THEN 1 END) as genomes_metadata_only,
                COUNT(CASE WHEN sequence_length IS NOT NULL AND sequence_length > 0 THEN 1 END) as genomes_with_size,
                MIN(CASE WHEN sequence_length > 0 THEN sequence_length END) as min_size,
                MAX(sequence_length) as max_size,
                AVG(CASE WHEN sequence_length > 0 THEN sequence_length END) as avg_size
            FROM genomes
            """
        )
        
        row = cursor.fetchone()
        genomes_with_files = row[0] if row else 0
        genomes_metadata_only = row[1] if row else 0
        genomes_with_size = row[2] if row else 0
        min_size = row[3] if row else None
        max_size = row[4] if row else None
        avg_size = row[5] if row else 0.0
        
        # Get breakdowns by type and source
        cursor = conn.execute(
            """
            SELECT sequence_type, source, COUNT(*) as count
            FROM genomes
            GROUP BY sequence_type, source
            """
        )
        
        sequence_types = {}
        sources = {}
        
        for row in cursor.fetchall():
            seq_type = row[0] or "unknown"
            source = row[1] or "unknown"
            count = row[2]
            
            sequence_types[seq_type] = sequence_types.get(seq_type, 0) + count
            sources[source] = sources.get(source, 0) + count
        
        genome_stats["genomes_with_files"] = genomes_with_files
        genome_stats["genomes_metadata_only"] = genomes_metadata_only
        
        # File validation (optimized with batching and threading for large datasets)
        if validate_files and genomes_with_files > 0:
            file_validation = {"accessible": 0, "missing": 0, "invalid": 0}
            
            # Get only file paths that need validation
            cursor = conn.execute(
                "SELECT file_path FROM genomes WHERE file_path IS NOT NULL AND file_path != ''"
            )
            file_paths = [row[0] for row in cursor.fetchall()]
            
            if len(file_paths) > 1000:
                # Use threading for large datasets
                file_validation = self._validate_files_batch(file_paths)
            else:
                # Use simple loop for smaller datasets
                for file_path in file_paths:
                    try:
                        path = Path(file_path)
                        if path.exists():
                            if path.is_file() and path.stat().st_size > 0:
                                file_validation["accessible"] += 1
                            else:
                                file_validation["invalid"] += 1
                        else:
                            file_validation["missing"] += 1
                    except (OSError, PermissionError):
                        file_validation["invalid"] += 1
            
            genome_stats["genome_file_validation"] = file_validation
        
        # For median calculation, we need individual values if we have size data
        median_size = 0
        if genomes_with_size > 0:
            if genomes_with_size <= 10000:  # Only calculate median for reasonable dataset sizes
                cursor = conn.execute(
                    "SELECT sequence_length FROM genomes WHERE sequence_length > 0 ORDER BY sequence_length"
                )
                lengths = [row[0] for row in cursor.fetchall()]
                median_size = statistics.median(lengths) if lengths else 0
            else:
                # Estimate median using percentile for very large datasets
                cursor = conn.execute(
                    """
                    SELECT sequence_length 
                    FROM genomes 
                    WHERE sequence_length > 0 
                    ORDER BY sequence_length 
                    LIMIT 1 OFFSET (
                        SELECT COUNT(*)/2 FROM genomes WHERE sequence_length > 0
                    )
                    """
                )
                result = cursor.fetchone()
                median_size = result[0] if result else 0
        
        # Genome size distribution
        genome_stats["genome_size_distribution"] = {
            "count": genomes_with_size,
            "min": min_size or 0,
            "max": max_size or 0,
            "avg": avg_size,
            "median": median_size
        }
        
        # Breakdowns
        genome_stats["sequence_type_breakdown"] = sequence_types
        genome_stats["source_distribution"] = sources
        
        return genome_stats

    def _validate_files_batch(self, file_paths: list) -> dict:
        """Validate files in batches using threading for better performance."""
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import os
        
        results = {}
        
        def validate_file(file_path):
            try:
                path = Path(file_path)
                exists = path.exists()
                accessible = False
                
                if exists:
                    try:
                        accessible = path.is_file() and path.stat().st_size > 0 and os.access(str(path), os.R_OK)
                    except (OSError, PermissionError):
                        accessible = False
                        
                return file_path, {"exists": exists, "accessible": accessible}
            except (OSError, PermissionError):
                return file_path, {"exists": False, "accessible": False}
        
        # Use ThreadPoolExecutor for I/O bound file validation
        batch_size = min(500, len(file_paths))  # Process in batches of 500
        
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as executor:
            for i in range(0, len(file_paths), batch_size):
                batch = file_paths[i:i + batch_size]
                futures = [executor.submit(validate_file, path) for path in batch]
                
                for future in as_completed(futures):
                    file_path, result = future.result()
                    results[file_path] = result
        
        return results

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
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('nodes', 'genomes')
            """
            )
            tables = set(row[0] for row in cursor.fetchall())

            if tables != {"nodes", "genomes"}:
                return False

            # Check that required columns exist in nodes table
            cursor = conn.execute("PRAGMA table_info(nodes)")
            node_columns = set(row[1] for row in cursor.fetchall())
            required_node_columns = {"tax_id", "name", "rank", "parent_id"}

            if not required_node_columns.issubset(node_columns):
                return False

            # Check that required columns exist in genomes table
            cursor = conn.execute("PRAGMA table_info(genomes)")
            genome_columns = set(row[1] for row in cursor.fetchall())
            required_genome_columns = {
                "genome_id",
                "tax_id",
                "file_path",
                "sequence_length",
                "sequence_type",
                "assembly_accession",
                "description",
                "source",
            }

            if not required_genome_columns.issubset(genome_columns):
                return False

            # Check foreign key constraints are enabled
            cursor = conn.execute("PRAGMA foreign_keys")
            if cursor.fetchone()[0] != 1:
                return False

            return True

        except sqlite3.Error:
            return False

    def get_sequence_tracker(self):
        """Get unified sequence tracker instance for this repository."""
        from .sequence_tracking import UnifiedSequenceTracker
        return UnifiedSequenceTracker(self)
    
    def get_sequence_manager(self):
        """Get unified sequence manager instance for this repository.""" 
        from ..sequence.unified_manager import UnifiedSequenceManager
        return UnifiedSequenceManager(self)
        
    def get_mapping_generator(self):
        """Get mapping file generator instance for this repository."""
        from ..sequence.mapping_generator import MappingFileGenerator
        return MappingFileGenerator(self)
    
    def sync_genomes_with_sequence_tracking(self) -> Dict[str, Any]:
        """Synchronize existing genomes with sequence tracking system.
        
        Returns:
            Dictionary with sync results
        """
        from ..sequence.sequence_tracker import SequenceTracker
        
        tracker = SequenceTracker(self)
        return tracker.sync_with_genomes()
    
    def register_sequence_files_from_directory(self, directory: Path, 
                                             file_type: str = "genome", 
                                             pattern: str = "*.fna") -> Dict[str, int]:
        """Register sequence files from a directory.
        
        Args:
            directory: Directory containing sequence files
            file_type: 'genome' for genomes, 'protein' for proteins
            pattern: Glob pattern for matching files
            
        Returns:
            Dictionary of {filename: file_id} for registered files
        """
        from ..sequence.sequence_tracker import SequenceTracker
        
        tracker = SequenceTracker(self)
        
        if file_type == "genome":
            return tracker.register_genomes(directory, pattern)
        elif file_type == "protein":
            return tracker.register_proteins(directory, pattern)
        else:
            raise ValueError(f"Invalid file_type: {file_type}. Use 'genome' or 'protein'")
    
    def generate_mapping_files(self, output_dir: Path, 
                              formats: Optional[List[str]] = None,
                              tool: Optional[str] = None,
                              prefix: str = '') -> Dict[str, int]:
        """Generate standard mapping files for sequence classification tools.
        
        Args:
            output_dir: Directory for output files
            formats: List of formats to generate (accession2taxid, nucl2taxid, prot2taxid, genome_sizes)
            tool: Generate tool-specific mappings (diamond, kraken2, mmseqs2, kaiju, centrifuge)
            prefix: Optional prefix for filenames
            
        Returns:
            Dictionary of {filename: count} for generated files
        """
        from ..sequence.sequence_tracker import SequenceTracker
        
        tracker = SequenceTracker(self)
        
        if tool:
            return tracker.generate_for_tool(tool, output_dir)
        else:
            return tracker.generate_mapping_files(output_dir, formats, prefix)
    
    def get_sequence_statistics(self) -> Dict[str, Any]:
        """Get comprehensive sequence tracking statistics.
        
        Returns:
            Dictionary with sequence file and protein statistics
        """
        from ..sequence.sequence_tracker import SequenceTracker
        
        tracker = SequenceTracker(self)
        stats = tracker.get_sequence_statistics()
        
        # Convert dataclass to dict for JSON serialization
        return {
            'total_files': stats.total_files,
            'genome_files': stats.genome_files,
            'protein_files': stats.protein_files,
            'taxa_with_genomes': stats.taxa_with_genomes,
            'taxa_with_proteins': stats.taxa_with_proteins,
            'total_sequences': stats.total_sequences,
            'total_proteins': stats.total_proteins,
            'file_validation_errors': stats.file_validation_errors or []
        }

    def get_node_by_name(self, name: str) -> Optional[TaxonomyNode]:
        """Get a taxonomy node by name.
        
        Args:
            name: The name of the node to find
            
        Returns:
            TaxonomyNode if found, None otherwise
        """
        conn = self._get_connection()
        
        try:
            cursor = conn.execute(
                "SELECT tax_id, name, rank, parent_id FROM nodes WHERE name = ?",
                (name,)
            )
            row = cursor.fetchone()
            
            if row:
                return TaxonomyNode(
                    tax_id=row[0],
                    name=row[1],
                    rank=TaxonomicRank(row[2]),
                    parent_id=row[3]
                )
            
            return None
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get node by name '{name}': {e}")

    def get_next_tax_id(self) -> int:
        """Get the next available taxonomy ID.
        
        Returns:
            Next available tax_id as integer
        """
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("SELECT MAX(tax_id) FROM nodes")
            result = cursor.fetchone()
            
            if result and result[0] is not None:
                return result[0] + 1
            else:
                return 1  # Start from 1 if no nodes exist
                
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get next tax_id: {e}")

    def get_genome(self, genome_id: str) -> Optional[GenomeInfo]:
        """Get genome information by genome ID.
        
        Args:
            genome_id: Unique genome identifier
            
        Returns:
            GenomeInfo if found, None otherwise
        """
        conn = self._get_connection()
        
        try:
            cursor = conn.execute(
                """
                SELECT genome_id, tax_id, file_path, sequence_length, 
                       sequence_type, assembly_accession, description, source
                FROM genomes 
                WHERE genome_id = ?
                """,
                (genome_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return GenomeInfo(
                    genome_id=row[0],
                    tax_id=row[1],
                    file_path=row[2],
                    sequence_length=row[3],
                    sequence_type=row[4],
                    assembly_accession=row[5],
                    description=row[6],
                    source=row[7],
                    # Default values for fields not in current database schema
                    nucleotide_accession=None,
                    protein_accession=None,
                    biosample_accession=None,
                    strain=None
                )
            
            return None
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get genome '{genome_id}': {e}")

    def update_genome(self, genome: GenomeInfo) -> None:
        """Update genome information in the database.
        
        Args:
            genome: Updated GenomeInfo object
        """
        conn = self._get_connection()
        
        try:
            conn.execute(
                """
                UPDATE genomes
                SET tax_id = ?, file_path = ?, sequence_length = ?,
                    sequence_type = ?, assembly_accession = ?, 
                    description = ?, source = ?
                WHERE genome_id = ?
                """,
                (
                    genome.tax_id,
                    genome.file_path,
                    genome.sequence_length,
                    genome.sequence_type,
                    genome.assembly_accession,
                    genome.description,
                    genome.source,
                    genome.genome_id
                )
            )
            
            if conn.total_changes == 0:
                raise DatabaseError(f"Genome '{genome.genome_id}' not found for update")
                
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to update genome '{genome.genome_id}': {e}")

    def get_ancestors(self, tax_id: int) -> List[TaxonomyNode]:
        """Get all ancestors of a node (from parent to root).
        
        Args:
            tax_id: Taxonomy ID to get ancestors for
            
        Returns:
            List of ancestor nodes in order from immediate parent to root
        """
        conn = self._get_connection()
        
        try:
            ancestors = []
            current_id = tax_id
            
            while True:
                cursor = conn.execute(
                    "SELECT parent_id FROM nodes WHERE tax_id = ?",
                    (current_id,)
                )
                result = cursor.fetchone()
                
                if not result or result[0] is None:
                    break
                    
                parent_id = result[0]
                parent_node = self.get_node(parent_id)
                
                if parent_node:
                    ancestors.append(parent_node)
                    current_id = parent_id
                else:
                    break
            
            return ancestors
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get ancestors for tax_id {tax_id}: {e}")

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def _insert_node_raw(self, conn: sqlite3.Connection, node: TaxonomyNode) -> None:
        """Insert a node without additional validation."""
        conn.execute(
            """
            INSERT INTO nodes (tax_id, name, rank, parent_id)
            VALUES (?, ?, ?, ?)
        """,
            (node.tax_id, node.name, node.rank.value, node.parent_id),
        )

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
    
    # Phase 1: Accession Management Methods
    
    def get_all_accession_mappings(self) -> List[Dict[str, Any]]:
        """Get all accession mappings from the database."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                SELECT accession, accession_version, tax_id, accession_type 
                FROM accession_mappings
                ORDER BY accession_type, accession
            """)
            
            mappings = []
            for row in cursor:
                mappings.append({
                    'accession': row[0],
                    'accession_version': row[1], 
                    'tax_id': row[2],
                    'accession_type': row[3]
                })
            
            return mappings
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get accession mappings: {e}")
    
    def get_accession_mappings_by_type(self, accession_type: str) -> List[Dict[str, Any]]:
        """Get accession mappings of a specific type."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                SELECT accession, accession_version, tax_id 
                FROM accession_mappings 
                WHERE accession_type = ?
                ORDER BY accession
            """, (accession_type,))
            
            mappings = []
            for row in cursor:
                mappings.append({
                    'accession': row[0],
                    'accession_version': row[1],
                    'tax_id': row[2]
                })
            
            return mappings
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get {accession_type} mappings: {e}")
    
    def get_missing_files_analysis(self) -> Dict[str, Any]:
        """Analyze what files are missing based on accession mappings."""
        conn = self._get_connection()
        
        try:
            # Get all accession mappings by type
            genome_accessions = self.get_accession_mappings_by_type('assembly')
            protein_accessions = self.get_accession_mappings_by_type('protein')
            nucleotide_accessions = self.get_accession_mappings_by_type('nucleotide')
            
            # Get existing genomes with file paths
            cursor = conn.execute("""
                SELECT g.tax_id, g.assembly_accession, g.file_path, g.genome_id
                FROM genomes g 
                WHERE g.file_path IS NOT NULL
            """)
            existing_genome_files = {row[1]: row for row in cursor if row[1]}  # assembly_accession -> row
            
            # Find missing genome files
            missing_genomes = []
            for mapping in genome_accessions:
                accession = mapping['accession']
                if accession not in existing_genome_files:
                    missing_genomes.append({
                        'accession': accession,
                        'accession_version': mapping['accession_version'],
                        'tax_id': mapping['tax_id'],
                        'type': 'genome'
                    })
            
            # TODO: Add protein file analysis when protein tracking is implemented
            missing_proteins = []
            
            # Get file status for existing files  
            file_issues = []
            for acc, file_info in existing_genome_files.items():
                file_path = file_info[2]  # file_path from row
                if file_path:
                    from pathlib import Path
                    path = Path(file_path)
                    if not path.exists():
                        file_issues.append({
                            'accession': acc,
                            'tax_id': file_info[0],
                            'file_path': file_path,
                            'issue': 'file_missing'
                        })
                    elif not path.is_file():
                        file_issues.append({
                            'accession': acc, 
                            'tax_id': file_info[0],
                            'file_path': file_path,
                            'issue': 'not_a_file'
                        })
            
            return {
                'missing_files': {
                    'genome': missing_genomes,
                    'protein': missing_proteins,
                    'nucleotide': []  # TODO: implement nucleotide tracking
                },
                'file_issues': file_issues,
                'summary': {
                    'total_accessions': len(genome_accessions) + len(protein_accessions) + len(nucleotide_accessions),
                    'genome_accessions': len(genome_accessions),
                    'existing_genome_files': len(existing_genome_files),
                    'missing_genome_files': len(missing_genomes),
                    'file_issues': len(file_issues)
                }
            }
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to analyze missing files: {e}")
    
    def add_accession_mappings(self, mappings: List[Dict[str, Any]]) -> int:
        """Add multiple accession mappings to the database."""
        conn = self._get_connection()
        
        try:
            added = 0
            for mapping in mappings:
                conn.execute("""
                    INSERT OR IGNORE INTO accession_mappings 
                    (accession, accession_version, tax_id, accession_type)
                    VALUES (?, ?, ?, ?)
                """, (
                    mapping['accession'],
                    mapping.get('accession_version'),
                    mapping['tax_id'], 
                    mapping['accession_type']
                ))
                if conn.changes > 0:
                    added += 1
            
            return added
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to add accession mappings: {e}")
    
    def register_sequence_file(self, sequence_file) -> int:
        """Register a sequence file and return its ID."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                INSERT INTO sequence_files (
                    file_path, file_type, scope, taxa_count, sequence_count,
                    file_exists, file_checksum, file_size, last_validated, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sequence_file.file_path,
                sequence_file.file_type,
                sequence_file.scope,
                sequence_file.taxa_count,
                sequence_file.sequence_count,
                sequence_file.file_exists,
                sequence_file.file_checksum,
                sequence_file.file_size,
                sequence_file.last_validated,
                sequence_file.created_date
            ))
            
            return cursor.lastrowid
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to register sequence file: {e}")
    
    def register_file_registry_entry(self, registry_entry) -> int:
        """Register a file registry entry and return its ID."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute("""
                INSERT INTO file_registry (
                    file_path, file_type, entity_id, tax_id, expected_path, actual_path,
                    exists, accessible, valid_format, size_bytes, checksum, last_checked,
                    issue_type, issue_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                registry_entry.file_path,
                registry_entry.file_type,
                registry_entry.entity_id,
                registry_entry.tax_id,
                registry_entry.expected_path,
                registry_entry.actual_path,
                registry_entry.exists,
                registry_entry.accessible,
                registry_entry.valid_format,
                registry_entry.size_bytes,
                registry_entry.checksum,
                registry_entry.last_checked,
                registry_entry.issue_type,
                getattr(registry_entry, 'issue_description', None)
            ))
            
            return cursor.lastrowid
            
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to register file registry entry: {e}")
    
    def get_comprehensive_genome_status(self) -> Dict[str, Any]:
        """Get comprehensive analysis of genome file status in the database."""
        conn = self._get_connection()
        
        try:
            # Work with the basic genomes table that exists
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_genomes,
                    COUNT(CASE WHEN g.file_path IS NOT NULL THEN 1 END) as with_file_paths,
                    COUNT(CASE WHEN g.file_path IS NULL THEN 1 END) as without_file_paths
                FROM genomes g
            """)
            
            basic_counts = cursor.fetchone()
            
            # Get genomes with file paths and check if files exist
            cursor = conn.execute("""
                SELECT 
                    g.genome_id, g.tax_id, g.file_path, g.assembly_accession,
                    n.name as tax_name
                FROM genomes g
                LEFT JOIN nodes n ON g.tax_id = n.tax_id
                WHERE g.file_path IS NOT NULL
                ORDER BY g.genome_id
            """)
            
            missing_with_paths = []
            valid_files_count = 0
            
            for row in cursor.fetchall():
                genome_id, tax_id, file_path, assembly_accession, tax_name = row
                
                # Check if file actually exists
                from pathlib import Path
                file_actually_exists = Path(file_path).exists() if file_path else False
                
                if not file_actually_exists:
                    missing_with_paths.append({
                        'genome_id': genome_id,
                        'tax_id': tax_id, 
                        'file_path': file_path,
                        'assembly_accession': assembly_accession,
                        'tax_name': tax_name,
                        'file_actually_exists': file_actually_exists
                    })
                else:
                    valid_files_count += 1
            
            # Get accessions that have mappings but no genome entries (truly missing)
            cursor = conn.execute("""
                SELECT DISTINCT
                    am.accession, am.tax_id, n.name as tax_name, am.accession_type
                FROM accession_mappings am
                LEFT JOIN nodes n ON am.tax_id = n.tax_id
                LEFT JOIN genomes g ON am.tax_id = g.tax_id AND g.assembly_accession = am.accession
                WHERE am.accession_type IN ('assembly', 'nucleotide')
                AND g.genome_id IS NULL
                ORDER BY am.accession
            """)
            
            truly_missing = []
            for row in cursor.fetchall():
                truly_missing.append({
                    'accession': row[0],
                    'tax_id': row[1],
                    'tax_name': row[2], 
                    'accession_type': row[3]
                })
            
            # Get count of files with accessions
            cursor = conn.execute("""
                SELECT COUNT(CASE WHEN g.assembly_accession IS NOT NULL THEN 1 END) as with_accessions
                FROM genomes g
                WHERE g.file_path IS NOT NULL
            """)
            accession_count = cursor.fetchone()
            valid_files_with_accessions = accession_count[0] if accession_count else 0
            
            return {
                'summary': {
                    'total_genomes': basic_counts[0] if basic_counts else 0,
                    'with_file_paths': basic_counts[1] if basic_counts else 0,
                    'without_file_paths': basic_counts[2] if basic_counts else 0, 
                    'files_exist': valid_files_count,
                    'files_missing': len(missing_with_paths),
                    'files_unchecked': 0,
                    'valid_files_total': valid_files_count,
                    'valid_files_with_accessions': valid_files_with_accessions
                },
                'missing_with_paths': missing_with_paths,  # Files that have paths but don't exist
                'truly_missing': truly_missing,            # Accessions without genome entries
                'downloadable_count': len(truly_missing)
            }
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error analyzing genome status: {e}")
            return {'summary': {}, 'missing_with_paths': [], 'truly_missing': [], 'downloadable_count': 0}
    
    def clean_missing_file_paths(self, verify_files: bool = True) -> Dict[str, Any]:
        """Clean file paths for genomes where files are missing.
        
        Args:
            verify_files: If True, verify file existence before cleaning paths
        
        Returns:
            Dictionary with cleaning results
        """
        conn = self._get_connection()
        
        try:
                # Use the basic genomes table that has the data
            table_name = "genomes"
            
            # Get genomes with file paths
            cursor = conn.execute(f"""
                SELECT genome_id, tax_id, file_path, assembly_accession
                FROM {table_name} 
                WHERE file_path IS NOT NULL
            """)
            
            genomes_to_clean = []
            genomes_checked = 0
            
            for row in cursor.fetchall():
                genome_id, tax_id, file_path, assembly_accession = row
                genomes_checked += 1
                
                should_clean = False
                if verify_files:
                    from pathlib import Path
                    if not Path(file_path).exists():
                        should_clean = True
                else:
                    should_clean = True
                
                if should_clean:
                    genomes_to_clean.append({
                        'genome_id': genome_id,
                        'tax_id': tax_id,
                        'file_path': file_path,
                        'assembly_accession': assembly_accession
                    })
            
            # Clean the paths
            cleaned_count = 0
            if genomes_to_clean:
                genome_ids = [g['genome_id'] for g in genomes_to_clean]
                
                # Build SQL with correct number of placeholders
                placeholders = ','.join(['?' for _ in genome_ids])
                
                # Use basic genomes table for UPDATE
                cursor = conn.execute(f"""
                    UPDATE genomes 
                    SET file_path = NULL
                    WHERE genome_id IN ({placeholders})
                """, genome_ids)
                
                cleaned_count = cursor.rowcount
            
            return {
                'genomes_checked': genomes_checked,
                'paths_cleaned': cleaned_count,
                'cleaned_genomes': genomes_to_clean[:10],  # Show first 10 as examples
                'total_cleaned': len(genomes_to_clean)
            }
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error cleaning file paths: {e}")
            raise DatabaseError(f"Failed to clean missing file paths: {e}")
