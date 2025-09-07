"""Command for automatically assigning accession IDs from node names."""

import argparse
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError
from ...core.models import TaxonomyNode, GenomeInfo
from ...database.sqlite import SQLiteTaxonomyRepository


logger = logging.getLogger(__name__)


class AccessionExtractor:
    """Extract accession IDs from node names using regex patterns."""
    
    # Comprehensive accession patterns for biological databases
    PATTERNS = {
        'assembly': {
            'pattern': r'(GC[FA]_\d{9}\.\d+)',
            'description': 'Assembly accessions (GCF/GCA)',
            'examples': ['GCF_000008985.1', 'GCA_006227905.1']
        },
        'nucleotide': {
            'pattern': r'((?:NC|NZ|CP|AP|AE|AL|AM|BA|BX|CM|FO|FP|FQ|FR)_\d+\.\d+)',
            'description': 'Nucleotide sequence accessions',
            'examples': ['NC_000913.3', 'NZ_CP012868.1', 'CP000001.1']
        },
        'protein': {
            'pattern': r'((?:WP|YP|NP|XP|AP)_\d+\.\d+)',
            'description': 'Protein sequence accessions',
            'examples': ['WP_000001234.1', 'YP_002344567.1', 'NP_414542.1']
        },
        'sra': {
            'pattern': r'((?:SRR|ERR|DRR)\d+)',
            'description': 'Sequence Read Archive accessions',
            'examples': ['SRR1234567', 'ERR987654', 'DRR555666']
        },
        'biosample': {
            'pattern': r'(SAM[NDE]\d+)',
            'description': 'BioSample accessions',
            'examples': ['SAMN12345678', 'SAMD00012345', 'SAME12345678']
        },
        'bioproject': {
            'pattern': r'(PRJ[NDE][A-Z]\d+)',
            'description': 'BioProject accessions',
            'examples': ['PRJNA123456', 'PRJEB789012', 'PRJDB345678']
        }
    }
    
    def __init__(self, accession_types: Optional[List[str]] = None):
        """Initialize extractor with specified accession types.
        
        Args:
            accession_types: List of accession types to extract. If None, extract all types.
        """
        self.accession_types = accession_types or list(self.PATTERNS.keys())
        self.compiled_patterns = {}
        
        # Compile regex patterns for efficiency
        for acc_type in self.accession_types:
            if acc_type in self.PATTERNS:
                self.compiled_patterns[acc_type] = re.compile(
                    self.PATTERNS[acc_type]['pattern'], re.IGNORECASE
                )
    
    def extract_accessions(self, node_name: str) -> Dict[str, List[str]]:
        """Extract all accessions from a node name.
        
        Args:
            node_name: Name of the taxonomic node
            
        Returns:
            Dictionary mapping accession types to lists of found accessions
        """
        accessions = defaultdict(list)
        
        for acc_type, pattern in self.compiled_patterns.items():
            matches = pattern.findall(node_name)
            if matches:
                # Remove duplicates while preserving order
                seen = set()
                unique_matches = []
                for match in matches:
                    if match not in seen:
                        seen.add(match)
                        unique_matches.append(match)
                accessions[acc_type] = unique_matches
        
        return dict(accessions)
    
    def validate_accession(self, accession: str, acc_type: str) -> bool:
        """Validate that an accession matches the expected pattern for its type.
        
        Args:
            accession: The accession to validate
            acc_type: The type of accession (assembly, nucleotide, etc.)
            
        Returns:
            True if valid, False otherwise
        """
        if acc_type not in self.PATTERNS:
            return False
            
        pattern = re.compile(self.PATTERNS[acc_type]['pattern'], re.IGNORECASE)
        return bool(pattern.match(accession))


class AssignAccessionsCommand(BaseCommand):
    """Command to automatically assign accession IDs from node names."""

    @classmethod
    def register_parser(cls, subparsers) -> argparse.ArgumentParser:
        """Register assign-accessions command parser."""
        parser = subparsers.add_parser(
            'assign-accessions',
            help='Automatically assign accession IDs from node names',
            description='Extract and assign accession IDs from taxonomic node names',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Extract all accession types from all nodes
  flextaxd assign-accessions --database my_db.ftd
  
  # Extract only assembly accessions, skip nodes with existing accessions
  flextaxd assign-accessions --database my_db.ftd --types assembly --conflict-strategy skip
  
  # Preview changes without making them
  flextaxd assign-accessions --database my_db.ftd --dry-run
  
  # Extract from nodes matching a pattern, overwrite existing accessions
  flextaxd assign-accessions --database my_db.ftd --node-filter "Francisella*" --conflict-strategy overwrite
  
  # Extract assembly and nucleotide accessions, create genome entries
  flextaxd assign-accessions --database my_db.ftd --types assembly nucleotide --create-genomes
  
  # Verbose output with detailed statistics
  flextaxd assign-accessions --database my_db.ftd --verbose --stats

Accession Types Supported:
  assembly    - GCF/GCA assembly accessions (GCF_000008985.1)
  nucleotide  - Chromosome/contig accessions (NC_000913.3, CP000001.1) 
  protein     - Protein sequence accessions (WP_000001234.1, YP_002344567.1)
  sra         - Sequence Read Archive (SRR1234567, ERR987654)
  biosample   - BioSample accessions (SAMN12345678, SAMD00012345)
  bioproject  - BioProject accessions (PRJNA123456, PRJEB789012)

Conflict Strategies:
  skip        - Skip nodes that already have accessions (default)
  overwrite   - Replace existing accessions with extracted ones
  append      - Add extracted accessions to existing ones
  merge       - Smart merge - add new types, keep existing of same type
            """,
        )

        parser.add_argument(
            '--database', '-d',
            type=Path,
            required=True,
            help='Path to FlexTaxD database file (.ftd)'
        )

        parser.add_argument(
            '--types', '-t',
            nargs='+',
            choices=['assembly', 'nucleotide', 'protein', 'sra', 'biosample', 'bioproject', 'all'],
            default=['all'],
            help='Accession types to extract (default: all)'
        )

        parser.add_argument(
            '--conflict-strategy',
            choices=['skip', 'overwrite', 'append', 'merge'],
            default='skip',
            help='How to handle nodes with existing accessions (default: skip)'
        )

        parser.add_argument(
            '--node-filter',
            help='Process only nodes whose names match this pattern (supports wildcards)'
        )

        parser.add_argument(
            '--create-genomes',
            action='store_true',
            help='Automatically create genome entries for nodes with assembly accessions'
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them'
        )

        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show detailed statistics about accession extraction'
        )

        parser.add_argument(
            '--validate-only',
            action='store_true',
            help='Only validate extracted accessions, don\'t assign them'
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute assign-accessions command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)
            
            # Determine accession types to extract
            accession_types = self._resolve_accession_types(args.types)
            
            # Initialize extractor
            extractor = AccessionExtractor(accession_types)
            
            # Load database
            with SQLiteTaxonomyRepository(args.database) as repository:
                # Get nodes to process
                nodes_to_process = self._get_nodes_to_process(repository, args.node_filter)
                
                if not nodes_to_process:
                    print("No nodes found to process")
                    return 0
                
                # Extract accessions from node names
                extraction_results = self._extract_accessions_from_nodes(
                    nodes_to_process, extractor, args.conflict_strategy
                )
                
                if args.stats or args.verbose:
                    self._print_extraction_statistics(extraction_results, extractor)
                
                if args.validate_only:
                    print("Validation complete - no changes made")
                    return 0
                
                if args.dry_run:
                    self._print_dry_run_summary(extraction_results)
                    return 0
                
                # Apply accession assignments
                changes_made = self._apply_accession_assignments(
                    repository, extraction_results, args.create_genomes
                )
                
                print(f"✅ Successfully processed {len(nodes_to_process)} nodes")
                print(f"✅ Made {changes_made} accession assignments")
                
                if args.create_genomes:
                    genome_count = self._create_genome_entries(repository, extraction_results)
                    if genome_count > 0:
                        print(f"✅ Created {genome_count} genome entries")
                
                return 0

        except ValidationError as e:
            logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except DatabaseError as e:
            logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            print(f"Error: {e}")
            return 1

    def _resolve_accession_types(self, types: List[str]) -> List[str]:
        """Resolve accession types from command line arguments."""
        if 'all' in types:
            return list(AccessionExtractor.PATTERNS.keys())
        return types

    def _get_nodes_to_process(self, repository: SQLiteTaxonomyRepository, 
                             node_filter: Optional[str]) -> List[TaxonomyNode]:
        """Get list of nodes to process based on filter."""
        # Load all nodes from database using repository method
        conn = repository._get_connection()
        all_nodes = []
        
        try:
            cursor = conn.execute(
                "SELECT tax_id, name, rank, parent_id FROM nodes ORDER BY tax_id"
            )
            
            for row in cursor:
                from ...core.models import TaxonomicRank
                rank = TaxonomicRank(row["rank"]) if row["rank"] else TaxonomicRank.CUSTOM
                
                node = TaxonomyNode(
                    tax_id=row["tax_id"],
                    name=row["name"],
                    rank=rank,
                    parent_id=row["parent_id"]
                )
                all_nodes.append(node)
                
        except Exception as e:
            raise DatabaseError(f"Failed to load nodes: {e}")
        
        # Apply filter if specified
        if node_filter:
            import fnmatch
            filtered_nodes = []
            for node in all_nodes:
                if fnmatch.fnmatch(node.name, node_filter):
                    filtered_nodes.append(node)
            return filtered_nodes
        
        return all_nodes

    def _extract_accessions_from_nodes(self, nodes: List[TaxonomyNode], 
                                     extractor: AccessionExtractor,
                                     conflict_strategy: str) -> Dict[str, Any]:
        """Extract accessions from node names and prepare assignment data."""
        results = {
            'nodes_processed': 0,
            'nodes_with_accessions': 0,
            'nodes_skipped': 0,
            'accessions_found': defaultdict(list),
            'assignments': [],
            'conflicts': [],
            'validation_errors': []
        }
        
        for node in nodes:
            results['nodes_processed'] += 1
            
            # Extract accessions from node name
            extracted_accessions = extractor.extract_accessions(node.name)
            
            if not extracted_accessions:
                continue
            
            results['nodes_with_accessions'] += 1
            
            # Check for existing accessions (this would need to be implemented in the repository)
            existing_accessions = self._get_existing_accessions(node)
            
            # Handle conflicts based on strategy
            final_accessions = self._resolve_accession_conflicts(
                extracted_accessions, existing_accessions, conflict_strategy
            )
            
            if not final_accessions:
                results['nodes_skipped'] += 1
                if existing_accessions:
                    results['conflicts'].append({
                        'node': node.name,
                        'existing': existing_accessions,
                        'extracted': extracted_accessions,
                        'reason': f'Skipped due to {conflict_strategy} strategy'
                    })
                continue
            
            # Validate all accessions
            valid_accessions = {}
            for acc_type, accessions in final_accessions.items():
                valid_accessions[acc_type] = []
                for accession in accessions:
                    if extractor.validate_accession(accession, acc_type):
                        valid_accessions[acc_type].append(accession)
                    else:
                        results['validation_errors'].append({
                            'node': node.name,
                            'accession': accession,
                            'type': acc_type,
                            'error': 'Invalid format'
                        })
            
            # Remove empty types
            valid_accessions = {k: v for k, v in valid_accessions.items() if v}
            
            if valid_accessions:
                results['assignments'].append({
                    'node': node,
                    'accessions': valid_accessions
                })
                
                # Track statistics
                for acc_type, accessions in valid_accessions.items():
                    results['accessions_found'][acc_type].extend(accessions)
        
        return results

    def _get_existing_accessions(self, node: TaxonomyNode) -> Dict[str, List[str]]:
        """Get existing accessions for a node."""
        # This would be called with repository access, but for now we'll 
        # implement a simple check later when we have repository context
        # In the actual implementation, this gets called from _extract_accessions_from_nodes
        # where we have repository access
        return {}

    def _resolve_accession_conflicts(self, extracted: Dict[str, List[str]], 
                                   existing: Dict[str, List[str]],
                                   strategy: str) -> Dict[str, List[str]]:
        """Resolve conflicts between extracted and existing accessions."""
        if not existing:
            return extracted
        
        if strategy == 'skip':
            return {}
        elif strategy == 'overwrite':
            return extracted
        elif strategy == 'append':
            result = existing.copy()
            for acc_type, accessions in extracted.items():
                if acc_type in result:
                    result[acc_type].extend(accessions)
                else:
                    result[acc_type] = accessions
            return result
        elif strategy == 'merge':
            result = existing.copy()
            for acc_type, accessions in extracted.items():
                if acc_type not in result:
                    result[acc_type] = accessions
                # For merge strategy, keep existing accessions of same type
            return result
        
        return extracted

    def _print_extraction_statistics(self, results: Dict[str, Any], 
                                   extractor: AccessionExtractor) -> None:
        """Print detailed statistics about accession extraction."""
        print("\n📊 Accession Extraction Statistics")
        print("=" * 50)
        print(f"Nodes processed: {results['nodes_processed']}")
        print(f"Nodes with accessions found: {results['nodes_with_accessions']}")
        print(f"Nodes skipped (conflicts): {results['nodes_skipped']}")
        print(f"Validation errors: {len(results['validation_errors'])}")
        
        print("\nAccessions found by type:")
        for acc_type in extractor.accession_types:
            count = len(results['accessions_found'][acc_type])
            unique_count = len(set(results['accessions_found'][acc_type]))
            print(f"  {acc_type:12}: {count:4} total, {unique_count:4} unique")
        
        if results['conflicts']:
            print(f"\n⚠️  {len(results['conflicts'])} conflict(s) encountered")
            
        if results['validation_errors']:
            print(f"\n❌ {len(results['validation_errors'])} validation error(s)")
            for error in results['validation_errors'][:5]:  # Show first 5
                print(f"  {error['node']}: {error['accession']} ({error['error']})")

    def _print_dry_run_summary(self, results: Dict[str, Any]) -> None:
        """Print summary of what would be changed in dry-run mode."""
        print("\n🔍 Dry-run Summary - No changes made")
        print("=" * 40)
        print(f"Would assign accessions to {len(results['assignments'])} nodes")
        
        if results['assignments'][:5]:  # Show first 5 examples
            print("\nExamples of assignments that would be made:")
            for assignment in results['assignments'][:5]:
                node_name = assignment['node'].name
                print(f"  {node_name}")
                for acc_type, accessions in assignment['accessions'].items():
                    for accession in accessions:
                        print(f"    → {acc_type}: {accession}")

    def _apply_accession_assignments(self, repository: SQLiteTaxonomyRepository,
                                   results: Dict[str, Any],
                                   create_genomes: bool) -> int:
        """Apply accession assignments to the database."""
        changes_made = 0
        conn = repository._get_connection()
        
        # Ensure the accession_mappings table exists (check existing schema first)
        try:
            # Check if table exists and what columns it has
            cursor = conn.execute("PRAGMA table_info(accession_mappings)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if not columns:
                # Table doesn't exist, create it with full schema
                conn.execute("""
                    CREATE TABLE accession_mappings (
                        accession TEXT PRIMARY KEY,
                        accession_version TEXT,
                        tax_id INTEGER NOT NULL,
                        accession_type TEXT,
                        source TEXT DEFAULT 'auto_assigned',
                        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (tax_id) REFERENCES nodes (tax_id) ON DELETE CASCADE
                    )
                """)
                columns = {'accession', 'accession_version', 'tax_id', 'accession_type', 'source', 'created_date'}
            
            # Add missing columns if needed
            if 'source' not in columns:
                conn.execute("ALTER TABLE accession_mappings ADD COLUMN source TEXT DEFAULT 'auto_assigned'")
            if 'created_date' not in columns:
                conn.execute("ALTER TABLE accession_mappings ADD COLUMN created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                
        except Exception as e:
            logger.warning(f"Could not modify accession_mappings table schema: {e}")
            # If we can't modify the schema, we'll work with what we have
        
        try:
            for assignment in results['assignments']:
                node = assignment['node']
                accessions = assignment['accessions']
                
                for acc_type, acc_list in accessions.items():
                    for accession in acc_list:
                        # Check if accession already exists
                        cursor = conn.execute(
                            "SELECT accession FROM accession_mappings WHERE accession = ?",
                            (accession,)
                        )
                        
                        if cursor.fetchone() is None:
                            # Insert new accession mapping (adapt to available columns)
                            if 'source' in columns:
                                conn.execute("""
                                    INSERT INTO accession_mappings 
                                    (accession, accession_version, tax_id, accession_type, source)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (accession, accession, node.tax_id, acc_type, 'auto_assigned'))
                            else:
                                # Basic insert without source column
                                conn.execute("""
                                    INSERT INTO accession_mappings 
                                    (accession, accession_version, tax_id, accession_type)
                                    VALUES (?, ?, ?, ?)
                                """, (accession, accession, node.tax_id, acc_type))
                            
                            changes_made += 1
                            
        except Exception as e:
            logger.error(f"Failed to apply accession assignments: {e}")
            raise DatabaseError(f"Failed to apply accession assignments: {e}")
        
        return changes_made

    def _create_genome_entries(self, repository: SQLiteTaxonomyRepository,
                             results: Dict[str, Any]) -> int:
        """Create genome entries for nodes with assembly accessions."""
        genomes_created = 0
        
        for assignment in results['assignments']:
            node = assignment['node']
            accessions = assignment['accessions']
            
            # Create genome entries for assembly accessions
            if 'assembly' in accessions:
                for assembly_acc in accessions['assembly']:
                    # Check if genome already exists
                    existing_genome = repository.get_genome(assembly_acc)
                    if not existing_genome:
                        # Create new genome entry
                        genome = GenomeInfo(
                            genome_id=assembly_acc,
                            tax_id=node.tax_id,
                            assembly_accession=assembly_acc,
                            description=f"Auto-created from {node.name}",
                            source="assigned_accessions_command"
                        )
                        repository.add_genome(genome)
                        genomes_created += 1
        
        return genomes_created