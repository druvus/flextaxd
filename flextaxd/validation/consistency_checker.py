"""Consistency checking utilities for database integrity."""

from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Any, Tuple, Callable
import logging
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import concurrent.futures

from ..core.models import TaxonomyTree, GenomeInfo
from ..database.repository import TaxonomyRepository
from ..core.exceptions import ValidationError


@dataclass  
class ConsistencyIssue:
    """A consistency issue found in the database."""
    category: str
    severity: str  # 'error', 'warning', 'info'
    description: str
    affected_items: List[str] = None
    
    def __post_init__(self):
        if self.affected_items is None:
            self.affected_items = []


class ConsistencyChecker:
    """Check data consistency across the entire database."""
    
    def __init__(self, repository: TaxonomyRepository, max_workers: int = 4):
        self.repository = repository
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        
    def check_full_consistency(self) -> Dict[str, Any]:
        """Perform comprehensive consistency check."""
        self.logger.info("Starting full consistency check")
        
        issues = []
        
        # Load data
        tree = self.repository.load_tree()
        genomes = self.repository.get_all_genomes()
        
        # Run all consistency checks with parallel processing for genome-related checks
        issues.extend(self._check_taxonomy_integrity(tree))
        issues.extend(self._check_genome_taxonomy_links(genomes, tree))
        
        # Use parallel processing for genome collection analysis
        if len(genomes) > 1000 and self.max_workers > 1:
            self.logger.info(f"Using parallel processing with {self.max_workers} workers for {len(genomes)} genomes")
            issues.extend(self._check_duplicate_genomes_parallel(genomes))
            issues.extend(self._check_orphaned_genomes_parallel(genomes, tree))
            issues.extend(self._check_sequence_type_consistency_parallel(genomes))
            issues.extend(self._check_source_consistency_parallel(genomes))
        else:
            issues.extend(self._check_duplicate_genomes(genomes))
            issues.extend(self._check_orphaned_genomes(genomes, tree))
            issues.extend(self._check_sequence_type_consistency(genomes))
            issues.extend(self._check_source_consistency(genomes))
        
        # Categorize issues
        report = self._generate_consistency_report(issues)
        report["total_nodes"] = tree.node_count
        report["total_genomes"] = len(genomes)
        
        self.logger.info(f"Consistency check complete: found {len(issues)} issues")
        
        return report
    
    def _check_taxonomy_integrity(self, tree: TaxonomyTree) -> List[ConsistencyIssue]:
        """Check taxonomy tree structural integrity."""
        issues = []
        
        # Check for cycles
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id):
            if node_id in rec_stack:
                return True
            if node_id in visited:
                return False
                
            visited.add(node_id)
            rec_stack.add(node_id)
            
            node = tree.get_node(node_id)
            if node and node.parent_id:
                if has_cycle(node.parent_id):
                    return True
            
            rec_stack.remove(node_id)
            return False
        
        # Check all nodes for cycles
        for node in tree:
            if node.tax_id not in visited:
                if has_cycle(node.tax_id):
                    issues.append(ConsistencyIssue(
                        category="taxonomy",
                        severity="error",
                        description="Circular reference detected in taxonomy tree",
                        affected_items=[str(node.tax_id)]
                    ))
        
        # Check for orphaned nodes (parent doesn't exist)
        for node in tree:
            if node.parent_id and not tree.get_node(node.parent_id):
                issues.append(ConsistencyIssue(
                    category="taxonomy", 
                    severity="error",
                    description=f"Node {node.tax_id} references non-existent parent {node.parent_id}",
                    affected_items=[str(node.tax_id)]
                ))
        
        # Check for multiple roots
        root_nodes = [node for node in tree if node.parent_id is None]
        if len(root_nodes) > 1:
            issues.append(ConsistencyIssue(
                category="taxonomy",
                severity="warning", 
                description=f"Multiple root nodes found: {len(root_nodes)}",
                affected_items=[str(node.tax_id) for node in root_nodes]
            ))
        elif len(root_nodes) == 0:
            issues.append(ConsistencyIssue(
                category="taxonomy",
                severity="error",
                description="No root node found in taxonomy tree",
                affected_items=[]
            ))
        
        # Check for duplicate names at same taxonomic level
        name_by_parent = {}
        for node in tree:
            parent_id = node.parent_id or "root"
            if parent_id not in name_by_parent:
                name_by_parent[parent_id] = {}
            
            if node.name in name_by_parent[parent_id]:
                issues.append(ConsistencyIssue(
                    category="taxonomy",
                    severity="warning",
                    description=f"Duplicate name '{node.name}' under same parent",
                    affected_items=[str(node.tax_id), str(name_by_parent[parent_id][node.name])]
                ))
            else:
                name_by_parent[parent_id][node.name] = node.tax_id
        
        return issues
    
    def _check_genome_taxonomy_links(self, genomes: List[GenomeInfo], tree: TaxonomyTree) -> List[ConsistencyIssue]:
        """Check that all genomes link to valid taxonomy nodes."""
        issues = []
        
        for genome in genomes:
            if not tree.get_node(genome.tax_id):
                issues.append(ConsistencyIssue(
                    category="genome_taxonomy",
                    severity="error", 
                    description=f"Genome {genome.genome_id} references non-existent taxonomy ID {genome.tax_id}",
                    affected_items=[genome.genome_id]
                ))
        
        return issues
    
    def _check_duplicate_genomes(self, genomes: List[GenomeInfo]) -> List[ConsistencyIssue]:
        """Check for duplicate genome entries."""
        issues = []
        
        # Check duplicate genome IDs
        genome_ids = set()
        for genome in genomes:
            if genome.genome_id in genome_ids:
                issues.append(ConsistencyIssue(
                    category="genome_duplicates",
                    severity="error",
                    description=f"Duplicate genome ID: {genome.genome_id}",
                    affected_items=[genome.genome_id]
                ))
            else:
                genome_ids.add(genome.genome_id)
        
        # Check duplicate file paths
        file_paths = {}
        for genome in genomes:
            if genome.file_path:
                if genome.file_path in file_paths:
                    issues.append(ConsistencyIssue(
                        category="genome_duplicates",
                        severity="warning",
                        description=f"Multiple genomes reference same file: {genome.file_path}",
                        affected_items=[genome.genome_id, file_paths[genome.file_path]]
                    ))
                else:
                    file_paths[genome.file_path] = genome.genome_id
        
        # Check duplicate assembly accessions
        accessions = {}
        for genome in genomes:
            if genome.assembly_accession:
                if genome.assembly_accession in accessions:
                    issues.append(ConsistencyIssue(
                        category="genome_duplicates",
                        severity="warning", 
                        description=f"Duplicate assembly accession: {genome.assembly_accession}",
                        affected_items=[genome.genome_id, accessions[genome.assembly_accession]]
                    ))
                else:
                    accessions[genome.assembly_accession] = genome.genome_id
        
        return issues
    
    def _check_orphaned_genomes(self, genomes: List[GenomeInfo], tree: TaxonomyTree) -> List[ConsistencyIssue]:
        """Check for genomes linked to leaf nodes that should have genome data."""
        issues = []
        
        # Find taxonomy nodes with genomes
        nodes_with_genomes = set(genome.tax_id for genome in genomes)
        
        # Find leaf nodes without genomes
        leaf_nodes_without_genomes = []
        for node in tree:
            children = tree.get_children(node.tax_id)
            if not children and node.tax_id not in nodes_with_genomes:
                # This is a leaf node with no genomes
                leaf_nodes_without_genomes.append(node.tax_id)
        
        if leaf_nodes_without_genomes:
            issues.append(ConsistencyIssue(
                category="orphaned_data",
                severity="info",
                description=f"Found {len(leaf_nodes_without_genomes)} leaf taxonomy nodes without genome data",
                affected_items=[str(tid) for tid in leaf_nodes_without_genomes[:10]]  # Limit display
            ))
        
        return issues
    
    def _check_sequence_type_consistency(self, genomes: List[GenomeInfo]) -> List[ConsistencyIssue]:
        """Check sequence type field consistency."""
        issues = []
        
        # Common valid sequence types
        valid_types = {'genome', 'chromosome', 'plasmid', 'contig', 'scaffold', '16S', 'rRNA', 'protein'}
        
        type_counts = {}
        invalid_types = set()
        
        for genome in genomes:
            seq_type = genome.sequence_type or "unknown"
            type_counts[seq_type] = type_counts.get(seq_type, 0) + 1
            
            if seq_type not in valid_types and seq_type != "unknown":
                invalid_types.add(seq_type)
        
        if invalid_types:
            issues.append(ConsistencyIssue(
                category="sequence_types",
                severity="warning",
                description=f"Non-standard sequence types found: {', '.join(sorted(invalid_types))}",
                affected_items=list(invalid_types)
            ))
        
        # Check for genomes without sequence type
        unknown_count = type_counts.get("unknown", 0)
        if unknown_count > 0:
            issues.append(ConsistencyIssue(
                category="sequence_types",
                severity="info",
                description=f"{unknown_count} genomes have unknown/missing sequence type",
                affected_items=[str(unknown_count)]
            ))
        
        return issues
    
    def _check_source_consistency(self, genomes: List[GenomeInfo]) -> List[ConsistencyIssue]:
        """Check source field consistency."""
        issues = []
        
        # Common valid sources
        valid_sources = {'NCBI', 'GTDB', 'SILVA', 'RefSeq', 'GenBank', 'custom', 'user'}
        
        source_counts = {}
        invalid_sources = set()
        
        for genome in genomes:
            source = genome.source or "unknown" 
            source_counts[source] = source_counts.get(source, 0) + 1
            
            if source not in valid_sources and source != "unknown":
                invalid_sources.add(source)
        
        if invalid_sources:
            issues.append(ConsistencyIssue(
                category="genome_sources", 
                severity="info",
                description=f"Non-standard genome sources found: {', '.join(sorted(invalid_sources))}",
                affected_items=list(invalid_sources)
            ))
        
        # Check for genomes without source
        unknown_count = source_counts.get("unknown", 0)
        if unknown_count > 0:
            issues.append(ConsistencyIssue(
                category="genome_sources",
                severity="info", 
                description=f"{unknown_count} genomes have unknown/missing source",
                affected_items=[str(unknown_count)]
            ))
        
        return issues
    
    def _generate_consistency_report(self, issues: List[ConsistencyIssue]) -> Dict[str, Any]:
        """Generate comprehensive consistency report."""
        # Categorize issues by severity
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"] 
        info = [i for i in issues if i.severity == "info"]
        
        # Group by category
        categories = {}
        for issue in issues:
            if issue.category not in categories:
                categories[issue.category] = []
            categories[issue.category].append(issue)
        
        report = {
            "summary": {
                "total_issues": len(issues),
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(info),
                "categories": len(categories)
            },
            "issues_by_severity": {
                "errors": [self._issue_to_dict(issue) for issue in errors],
                "warnings": [self._issue_to_dict(issue) for issue in warnings], 
                "info": [self._issue_to_dict(issue) for issue in info]
            },
            "issues_by_category": {
                category: [self._issue_to_dict(issue) for issue in category_issues]
                for category, category_issues in categories.items()
            },
            "consistency_score": self._calculate_consistency_score(issues)
        }
        
        return report
    
    def _issue_to_dict(self, issue: ConsistencyIssue) -> Dict[str, Any]:
        """Convert consistency issue to dictionary."""
        return {
            "category": issue.category,
            "severity": issue.severity,
            "description": issue.description,
            "affected_count": len(issue.affected_items),
            "affected_items": issue.affected_items[:5]  # Limit for readability
        }
    
    def _calculate_consistency_score(self, issues: List[ConsistencyIssue]) -> float:
        """Calculate overall consistency score (0-100)."""
        if not issues:
            return 100.0
        
        # Weight different severities
        error_weight = 10
        warning_weight = 3  
        info_weight = 1
        
        total_weight = 0
        for issue in issues:
            if issue.severity == "error":
                total_weight += error_weight
            elif issue.severity == "warning":
                total_weight += warning_weight
            else:
                total_weight += info_weight
        
        # Score decreases based on weighted issues
        # Maximum penalty assumed to be 50 weighted issues for 0 score
        max_penalty = 50 * error_weight
        score = max(0, 100 - (total_weight / max_penalty * 100))
        
        return round(score, 2)
    
    # Parallel processing methods for large-scale validation
    
    def _check_duplicate_genomes_parallel(self, genomes: List[GenomeInfo]) -> List[ConsistencyIssue]:
        """Check for duplicate genomes using parallel processing."""
        issues = []
        
        if len(genomes) < 2:
            return issues
        
        # Chunk genomes for parallel processing
        chunk_size = max(1, len(genomes) // self.max_workers)
        genome_chunks = [genomes[i:i + chunk_size] for i in range(0, len(genomes), chunk_size)]
        
        duplicate_sets = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks to check for duplicates within chunks
            future_to_chunk = {
                executor.submit(self._find_duplicates_in_chunk, chunk, i): i 
                for i, chunk in enumerate(genome_chunks)
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                try:
                    chunk_duplicates = future.result()
                    duplicate_sets.extend(chunk_duplicates)
                except Exception as e:
                    self.logger.error(f"Error processing genome chunk {chunk_index}: {e}")
        
        # Also check for duplicates across chunks (this requires cross-chunk comparison)
        cross_chunk_duplicates = self._find_cross_chunk_duplicates(genome_chunks)
        duplicate_sets.extend(cross_chunk_duplicates)
        
        # Convert duplicate sets to issues
        for dup_set in duplicate_sets:
            if len(dup_set) > 1:
                issues.append(ConsistencyIssue(
                    category="duplicate_genomes",
                    severity="warning", 
                    description=f"Found {len(dup_set)} duplicate genomes",
                    affected_items=[g.genome_id for g in dup_set]
                ))
        
        return issues
    
    def _find_duplicates_in_chunk(self, chunk: List[GenomeInfo], chunk_index: int) -> List[List[GenomeInfo]]:
        """Find duplicates within a single chunk of genomes."""
        duplicates = []
        seen = {}
        
        for genome in chunk:
            key = (genome.genome_id, genome.tax_id, genome.file_path)
            if key in seen:
                # Found duplicate
                if seen[key] not in [d[0] for d in duplicates]:
                    duplicates.append([seen[key], genome])
                else:
                    # Add to existing duplicate group
                    for dup_group in duplicates:
                        if seen[key] in dup_group:
                            dup_group.append(genome)
                            break
            else:
                seen[key] = genome
        
        return duplicates
    
    def _find_cross_chunk_duplicates(self, chunks: List[List[GenomeInfo]]) -> List[List[GenomeInfo]]:
        """Find duplicates across different chunks (simplified approach)."""
        # For large datasets, this could be optimized with more sophisticated algorithms
        # For now, use a simpler approach suitable for moderate cross-chunk duplication
        all_genomes_map = {}
        duplicates = []
        
        for chunk in chunks:
            for genome in chunk:
                key = (genome.genome_id, genome.tax_id, genome.file_path)
                if key in all_genomes_map:
                    # Found cross-chunk duplicate
                    existing_genome = all_genomes_map[key]
                    duplicates.append([existing_genome, genome])
                else:
                    all_genomes_map[key] = genome
        
        return duplicates
    
    def _check_sequence_type_consistency_parallel(self, genomes: List[GenomeInfo]) -> List[ConsistencyIssue]:
        """Check sequence type consistency using parallel processing."""
        chunk_size = max(1, len(genomes) // self.max_workers)
        genome_chunks = [genomes[i:i + chunk_size] for i in range(0, len(genomes), chunk_size)]
        
        all_type_counts = {}
        all_invalid_types = set()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._analyze_sequence_types_chunk, chunk): chunk
                for chunk in genome_chunks
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                try:
                    type_counts, invalid_types = future.result()
                    
                    # Merge results
                    for seq_type, count in type_counts.items():
                        all_type_counts[seq_type] = all_type_counts.get(seq_type, 0) + count
                    all_invalid_types.update(invalid_types)
                    
                except Exception as e:
                    self.logger.error(f"Error analyzing sequence types: {e}")
        
        # Generate issues from merged results
        issues = []
        if all_invalid_types:
            issues.append(ConsistencyIssue(
                category="sequence_types",
                severity="warning",
                description=f"Non-standard sequence types found: {', '.join(sorted(all_invalid_types))}",
                affected_items=list(all_invalid_types)
            ))
        
        unknown_count = all_type_counts.get("unknown", 0)
        if unknown_count > 0:
            issues.append(ConsistencyIssue(
                category="sequence_types",
                severity="info",
                description=f"{unknown_count} genomes have unknown/missing sequence type",
                affected_items=[str(unknown_count)]
            ))
        
        return issues
    
    def _analyze_sequence_types_chunk(self, chunk: List[GenomeInfo]) -> Tuple[Dict[str, int], Set[str]]:
        """Analyze sequence types in a chunk of genomes."""
        valid_types = {'genome', 'chromosome', 'plasmid', 'contig', 'scaffold', '16S', 'rRNA', 'protein'}
        type_counts = {}
        invalid_types = set()
        
        for genome in chunk:
            seq_type = genome.sequence_type or "unknown"
            type_counts[seq_type] = type_counts.get(seq_type, 0) + 1
            
            if seq_type not in valid_types and seq_type != "unknown":
                invalid_types.add(seq_type)
        
        return type_counts, invalid_types
    
    def _check_source_consistency_parallel(self, genomes: List[GenomeInfo]) -> List[ConsistencyIssue]:
        """Check source consistency using parallel processing."""
        chunk_size = max(1, len(genomes) // self.max_workers)
        genome_chunks = [genomes[i:i + chunk_size] for i in range(0, len(genomes), chunk_size)]
        
        all_source_counts = {}
        all_invalid_sources = set()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._analyze_sources_chunk, chunk): chunk
                for chunk in genome_chunks
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                try:
                    source_counts, invalid_sources = future.result()
                    
                    # Merge results
                    for source, count in source_counts.items():
                        all_source_counts[source] = all_source_counts.get(source, 0) + count
                    all_invalid_sources.update(invalid_sources)
                    
                except Exception as e:
                    self.logger.error(f"Error analyzing sources: {e}")
        
        # Generate issues from merged results
        issues = []
        if all_invalid_sources:
            issues.append(ConsistencyIssue(
                category="genome_sources",
                severity="info",
                description=f"Non-standard genome sources found: {', '.join(sorted(all_invalid_sources))}",
                affected_items=list(all_invalid_sources)
            ))
        
        unknown_count = all_source_counts.get("unknown", 0)
        if unknown_count > 0:
            issues.append(ConsistencyIssue(
                category="genome_sources",
                severity="info",
                description=f"{unknown_count} genomes have unknown/missing source",
                affected_items=[str(unknown_count)]
            ))
        
        return issues
    
    def _analyze_sources_chunk(self, chunk: List[GenomeInfo]) -> Tuple[Dict[str, int], Set[str]]:
        """Analyze sources in a chunk of genomes."""
        valid_sources = {'NCBI', 'GTDB', 'SILVA', 'RefSeq', 'GenBank', 'custom', 'user'}
        source_counts = {}
        invalid_sources = set()
        
        for genome in chunk:
            source = genome.source or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1
            
            if source not in valid_sources and source != "unknown":
                invalid_sources.add(source)
        
        return source_counts, invalid_sources
    
    def _check_orphaned_genomes_parallel(self, genomes: List[GenomeInfo], tree: TaxonomyTree) -> List[ConsistencyIssue]:
        """Check for orphaned genomes using parallel processing."""
        issues = []
        
        # Create a set of all genome tax_ids for faster lookup
        genome_tax_ids = set(genome.tax_id for genome in genomes)
        
        # Get all nodes and chunk them for parallel processing
        all_nodes = list(tree)
        chunk_size = max(1, len(all_nodes) // self.max_workers)
        node_chunks = [all_nodes[i:i + chunk_size] for i in range(0, len(all_nodes), chunk_size)]
        
        all_leaf_nodes_without_genomes = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._find_leaf_nodes_without_genomes_chunk, chunk, tree, genome_tax_ids): chunk
                for chunk in node_chunks
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                try:
                    leaf_nodes_without_genomes = future.result()
                    all_leaf_nodes_without_genomes.extend(leaf_nodes_without_genomes)
                except Exception as e:
                    self.logger.error(f"Error finding orphaned genomes: {e}")
        
        if all_leaf_nodes_without_genomes:
            issues.append(ConsistencyIssue(
                category="orphaned_data",
                severity="info",
                description=f"Found {len(all_leaf_nodes_without_genomes)} leaf taxonomy nodes without genome data",
                affected_items=[str(tid) for tid in all_leaf_nodes_without_genomes[:10]]
            ))
        
        return issues
    
    def _find_leaf_nodes_without_genomes_chunk(self, chunk, tree: TaxonomyTree, genome_tax_ids: Set[int]) -> List[int]:
        """Find leaf nodes without genomes in a chunk of nodes."""
        leaf_nodes_without_genomes = []
        
        for node in chunk:
            children = tree.get_children(node.tax_id)
            if not children and node.tax_id not in genome_tax_ids:
                leaf_nodes_without_genomes.append(node.tax_id)
        
        return leaf_nodes_without_genomes