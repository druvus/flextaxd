"""Core domain models for taxonomy representation."""

from __future__ import annotations
from typing import Optional, Dict, Set, List, Iterator, Any
from dataclasses import dataclass, field
from enum import Enum


class TaxonomicRank(Enum):
    """Standard taxonomic ranks."""

    ROOT = "root"
    SUPERKINGDOM = "superkingdom"
    KINGDOM = "kingdom"
    PHYLUM = "phylum"
    CLASS = "class"
    ORDER = "order"
    FAMILY = "family"
    GENUS = "genus"
    SPECIES = "species"
    SUBSPECIES = "subspecies"
    STRAIN = "strain"
    CUSTOM = "custom"


@dataclass(frozen=True)
class TaxonomyNode:
    """Represents a single node in the taxonomy tree."""

    tax_id: int
    name: str
    rank: TaxonomicRank = TaxonomicRank.CUSTOM
    parent_id: Optional[int] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate node data after initialization."""
        if self.tax_id <= 0:
            raise ValueError(f"Tax ID must be positive, got {self.tax_id}")
        if not self.name.strip():
            raise ValueError("Node name cannot be empty")
        if self.parent_id is not None and self.parent_id <= 0:
            raise ValueError(f"Parent ID must be positive, got {self.parent_id}")
        if self.parent_id == self.tax_id:
            raise ValueError("Node cannot be its own parent")


@dataclass(frozen=True)
class GenomeInfo:
    """Information about a genome associated with a taxonomic node.
    
    Supports multiple types of accessions and allows multiple genomes
    to be associated with the same taxonomic node (e.g., multiple strains
    of the same species).
    
    Accession Types Supported:
    - Assembly: GCF_/GCA_ (RefSeq/GenBank assemblies)
    - Nucleotide: NC_/NZ_/CP_ (chromosome/contig sequences)  
    - Protein: WP_/YP_/NP_ (protein sequences)
    - BioSample: SAMN_/SAMD_/SAME_ (sample metadata)
    
    Example:
        # Multiple E. coli genomes for the same species node
        ecoli_k12 = GenomeInfo(
            genome_id="ecoli_k12_mg1655",
            tax_id=511145,  # E. coli str. K-12 substr. MG1655
            assembly_accession="GCF_000005825.2",
            strain="K-12 substr. MG1655",
            source="NCBI"
        )
    """

    genome_id: str
    tax_id: int
    file_path: Optional[str] = None
    sequence_length: Optional[int] = None
    sequence_type: Optional[str] = None  # e.g., 'genome', '16S', 'plasmid', 'protein'
    assembly_accession: Optional[str] = None  # GCF_/GCA_ accessions
    nucleotide_accession: Optional[str] = None  # NC_/NZ_/CP_ accessions
    protein_accession: Optional[str] = None  # WP_/YP_/NP_ accessions
    biosample_accession: Optional[str] = None  # SAMN_/SAMD_/SAME_ accessions
    description: Optional[str] = None
    source: Optional[str] = None  # e.g., 'NCBI', 'GTDB', 'SILVA'
    strain: Optional[str] = None  # Strain/isolate information
    file_checksum: Optional[str] = None  # MD5 checksum for file integrity verification

    def __post_init__(self) -> None:
        """Validate genome info after initialization."""
        if not self.genome_id.strip():
            raise ValueError("Genome ID cannot be empty")
        if self.tax_id is not None and self.tax_id <= 0:
            raise ValueError(f"Tax ID must be positive, got {self.tax_id}")

    def validate(self) -> List[str]:
        """Validate genome information."""
        issues = []

        if not self.genome_id:
            issues.append("Genome ID cannot be empty")

        if self.tax_id <= 0:
            issues.append("Taxonomy ID must be positive")

        if self.file_path:
            from pathlib import Path

            path = Path(self.file_path)
            if not path.exists():
                issues.append(f"Sequence file does not exist: {self.file_path}")

        return issues

    @property
    def has_sequence_file(self) -> bool:
        """Check if genome has an associated sequence file."""
        if not self.file_path:
            return False
        from pathlib import Path

        return Path(self.file_path).exists()

    @property
    def file_size(self) -> Optional[int]:
        """Get size of sequence file in bytes."""
        if self.has_sequence_file and self.file_path:
            try:
                from pathlib import Path

                return Path(self.file_path).stat().st_size
            except OSError:
                pass
        return None

    @property
    def all_accessions(self) -> Dict[str, str]:
        """Get all available accessions for this genome."""
        accessions = {}
        if self.assembly_accession:
            accessions['assembly'] = self.assembly_accession
        if self.nucleotide_accession:
            accessions['nucleotide'] = self.nucleotide_accession
        if self.protein_accession:
            accessions['protein'] = self.protein_accession
        if self.biosample_accession:
            accessions['biosample'] = self.biosample_accession
        return accessions

    @property 
    def primary_accession(self) -> Optional[str]:
        """Get the primary accession (preference: assembly > nucleotide > protein > biosample)."""
        if self.assembly_accession:
            return self.assembly_accession
        if self.nucleotide_accession:
            return self.nucleotide_accession
        if self.protein_accession:
            return self.protein_accession
        if self.biosample_accession:
            return self.biosample_accession
        return None

    def validate_accessions(self) -> List[str]:
        """Validate accession number formats."""
        import re
        issues = []
        
        # Assembly accession patterns (GCF_/GCA_)
        if self.assembly_accession and not re.match(r'^GC[FA]_\d{9}\.\d+$', self.assembly_accession):
            issues.append(f"Invalid assembly accession format: {self.assembly_accession}")
        
        # Nucleotide accession patterns (NC_/NZ_/CP_/AP_)
        if self.nucleotide_accession and not re.match(r'^(NC|NZ|CP|AP)_\d+\.\d+$', self.nucleotide_accession):
            issues.append(f"Invalid nucleotide accession format: {self.nucleotide_accession}")
        
        # Protein accession patterns (WP_/YP_/NP_)
        if self.protein_accession and not re.match(r'^(WP|YP|NP)_\d+\.\d+$', self.protein_accession):
            issues.append(f"Invalid protein accession format: {self.protein_accession}")
        
        
        # BioSample accession patterns (SAMN_/SAMD_/SAME_)
        if self.biosample_accession and not re.match(r'^SAM[NDE][A-Z]?\d+$', self.biosample_accession):
            issues.append(f"Invalid BioSample accession format: {self.biosample_accession}")
        
        return issues


class TaxonomyTree:
    """Represents a complete taxonomy tree with validation and operations."""

    def __init__(self) -> None:
        self._nodes: Dict[int, TaxonomyNode] = {}
        self._children: Dict[int, Set[int]] = {}
        self._genomes: Dict[str, GenomeInfo] = {}
        self._root_id: Optional[int] = None

    def add_node(self, node: TaxonomyNode) -> None:
        """Add a node to the tree with validation."""
        if node.tax_id in self._nodes:
            raise ValueError(f"Node with ID {node.tax_id} already exists")

        # Validate parent exists (except for root)
        if node.parent_id is not None:
            if node.parent_id not in self._nodes:
                raise ValueError(f"Parent node {node.parent_id} does not exist")

            # Check for circular references
            if self._would_create_cycle(node.tax_id, node.parent_id):
                raise ValueError("Adding node would create circular reference")
        else:
            # This is a root node
            if self._root_id is not None:
                raise ValueError("Tree already has a root node")
            self._root_id = node.tax_id

        self._nodes[node.tax_id] = node

        # Update parent-child relationships
        if node.parent_id is not None:
            if node.parent_id not in self._children:
                self._children[node.parent_id] = set()
            self._children[node.parent_id].add(node.tax_id)

    def get_node(self, tax_id: int) -> Optional[TaxonomyNode]:
        """Get a node by its taxonomic ID."""
        return self._nodes.get(tax_id)

    def get_children(self, tax_id: int) -> Set[int]:
        """Get all direct children of a node."""
        return self._children.get(tax_id, set()).copy()

    def get_descendants(self, tax_id: int) -> Set[int]:
        """Get all descendants (children, grandchildren, etc.) of a node."""
        descendants = set()
        queue = list(self.get_children(tax_id))

        while queue:
            child_id = queue.pop(0)
            if child_id not in descendants:
                descendants.add(child_id)
                queue.extend(self.get_children(child_id))

        return descendants

    def get_path_to_root(self, tax_id: int) -> List[TaxonomyNode]:
        """Get the path from a node to the root."""
        path = []
        current_id: Optional[int] = tax_id

        while current_id is not None:
            node = self.get_node(current_id)
            if node is None:
                break
            path.append(node)
            current_id = node.parent_id

        return path

    def remove_node(self, tax_id: int, reassign_children: bool = True) -> None:
        """Remove a node from the tree."""
        node = self.get_node(tax_id)
        if node is None:
            raise ValueError(f"Node {tax_id} does not exist")

        children = self.get_children(tax_id)

        if children and not reassign_children:
            raise ValueError(f"Cannot remove node {tax_id}: has children")

        # Reassign children to this node's parent
        if reassign_children and children:
            for child_id in children:
                child_node = self._nodes[child_id]
                # Create new node with updated parent
                updated_child = TaxonomyNode(
                    tax_id=child_node.tax_id,
                    name=child_node.name,
                    rank=child_node.rank,
                    parent_id=node.parent_id,
                )
                self._nodes[child_id] = updated_child

            # Update parent's children list
            if node.parent_id is not None:
                self._children[node.parent_id].update(children)
                self._children[node.parent_id].discard(tax_id)

        # Remove from parent's children
        if node.parent_id is not None:
            self._children[node.parent_id].discard(tax_id)

        # Clean up
        del self._nodes[tax_id]
        if tax_id in self._children:
            del self._children[tax_id]

        # Update root if necessary
        if tax_id == self._root_id:
            self._root_id = None

    def add_genome(self, genome: GenomeInfo) -> None:
        """Add genome information."""
        if genome.tax_id not in self._nodes:
            raise ValueError(f"Taxonomic node {genome.tax_id} does not exist")

        self._genomes[genome.genome_id] = genome

    def get_genomes_for_node(self, tax_id: int) -> List[GenomeInfo]:
        """Get all genomes associated with a taxonomic node."""
        return [g for g in self._genomes.values() if g.tax_id == tax_id]

    def validate_tree(self) -> List[str]:
        """Validate the entire tree structure and return list of issues."""
        issues = []

        # Check for orphaned nodes
        for node in self._nodes.values():
            if node.parent_id is not None and node.parent_id not in self._nodes:
                issues.append(f"Node {node.tax_id} has missing parent {node.parent_id}")

        # Check for cycles (should not happen with our validation, but double-check)
        visited: set[int] = set()
        for node_id in self._nodes:
            if self._has_cycle_from_node(node_id, visited):
                issues.append(f"Cycle detected involving node {node_id}")

        return issues

    def _would_create_cycle(self, new_node_id: int, parent_id: int) -> bool:
        """Check if adding a node with given parent would create a cycle."""
        current_id: Optional[int] = parent_id
        while current_id is not None:
            if current_id == new_node_id:
                return True
            current_node = self.get_node(current_id)
            if current_node is None:
                break
            current_id = current_node.parent_id
        return False

    def _has_cycle_from_node(self, start_id: int, global_visited: set[int]) -> bool:
        """Check for cycles starting from a specific node."""
        if start_id in global_visited:
            return False

        visited: set[int] = set()
        current_id: Optional[int] = start_id

        while current_id is not None:
            if current_id in visited:
                return True
            visited.add(current_id)

            node = self.get_node(current_id)
            if node is None:
                break
            current_id = node.parent_id

        global_visited.update(visited)
        return False

    @property
    def node_count(self) -> int:
        """Get the total number of nodes in the tree."""
        return len(self._nodes)

    @property
    def genome_count(self) -> int:
        """Get the total number of genomes."""
        return len(self._genomes)

    @property
    def root_id(self) -> Optional[int]:
        """Get the root node ID."""
        return self._root_id

    def __iter__(self) -> Iterator[TaxonomyNode]:
        """Iterate over all nodes in the tree."""
        return iter(self._nodes.values())

    def __len__(self) -> int:
        """Get the number of nodes in the tree."""
        return len(self._nodes)

    def __contains__(self, tax_id: int) -> bool:
        """Check if a taxonomic ID exists in the tree."""
        return tax_id in self._nodes

    # ==== ADVANCED TREE OPERATIONS ====

    def lowest_common_ancestor(self, *tax_ids: int) -> Optional[TaxonomyNode]:
        """Find the Lowest Common Ancestor (LCA) of given taxonomic IDs.

        Args:
            tax_ids: Variable number of taxonomic IDs to find LCA for

        Returns:
            TaxonomyNode of the LCA, or None if no common ancestor exists

        Time complexity: O(h * n) where h is height and n is number of nodes
        """
        if not tax_ids:
            return None

        if len(tax_ids) == 1:
            return self.get_node(tax_ids[0])

        # Get paths to root for all nodes
        paths = []
        for tax_id in tax_ids:
            if tax_id not in self._nodes:
                return None
            path = self.get_path_to_root(tax_id)
            if not path:
                return None
            # Reverse to go from root to leaf
            paths.append(path[::-1])

        # Find common prefix (LCA is the last common node)
        min_length = min(len(path) for path in paths)
        lca_node = None

        for i in range(min_length):
            current_nodes = [path[i] for path in paths]
            if all(node.tax_id == current_nodes[0].tax_id for node in current_nodes):
                lca_node = current_nodes[0]
            else:
                break

        return lca_node

    def taxonomic_distance(self, tax_id1: int, tax_id2: int) -> Optional[int]:
        """Calculate taxonomic distance between two nodes.

        Distance is measured as the sum of steps from each node to their LCA.

        Args:
            tax_id1: First taxonomic ID
            tax_id2: Second taxonomic ID

        Returns:
            Distance as integer, or None if nodes don't exist or have no LCA
        """
        if tax_id1 not in self._nodes or tax_id2 not in self._nodes:
            return None

        if tax_id1 == tax_id2:
            return 0

        lca = self.lowest_common_ancestor(tax_id1, tax_id2)
        if lca is None:
            return None

        # Calculate distance from each node to LCA
        path1 = self.get_path_to_root(tax_id1)
        path2 = self.get_path_to_root(tax_id2)

        # Find position of LCA in each path
        lca_pos1 = next(
            (i for i, node in enumerate(path1) if node.tax_id == lca.tax_id), None
        )
        lca_pos2 = next(
            (i for i, node in enumerate(path2) if node.tax_id == lca.tax_id), None
        )

        if lca_pos1 is None or lca_pos2 is None:
            return None

        return lca_pos1 + lca_pos2

    def extract_subtree(
        self, root_tax_id: int, preserve_tax_ids: bool = True
    ) -> "TaxonomyTree":
        """Extract a complete subtree rooted at the given node.

        Args:
            root_tax_id: The root of the subtree to extract
            preserve_tax_ids: If True, keep original tax_ids. If False, reassign sequentially.

        Returns:
            New TaxonomyTree containing the subtree
        """
        if root_tax_id not in self._nodes:
            raise ValueError(f"Node {root_tax_id} does not exist")

        # Get all descendants plus the root
        descendants = self.get_descendants(root_tax_id)
        subtree_nodes = {root_tax_id} | descendants

        # Create new tree
        new_tree = TaxonomyTree()
        id_mapping = {}

        if not preserve_tax_ids:
            # Create sequential ID mapping
            for i, old_id in enumerate(sorted(subtree_nodes), start=1):
                id_mapping[old_id] = i
        else:
            # Preserve original IDs
            id_mapping = {old_id: old_id for old_id in subtree_nodes}

        # Add nodes in dependency order (parents before children)
        nodes_to_add = list(subtree_nodes)

        # Sort by depth (root first)
        def get_depth(tax_id: int) -> int:
            depth = 0
            current = self.get_node(tax_id)
            while (
                current
                and current.parent_id is not None
                and current.parent_id in subtree_nodes
            ):
                depth += 1
                current = self.get_node(current.parent_id)
            return depth

        nodes_to_add.sort(key=get_depth)

        for old_id in nodes_to_add:
            old_node = self._nodes[old_id]
            new_id = id_mapping[old_id]

            # Determine new parent ID
            new_parent_id = None
            if old_node.parent_id is not None and old_node.parent_id in subtree_nodes:
                new_parent_id = id_mapping[old_node.parent_id]

            new_node = TaxonomyNode(
                tax_id=new_id,
                name=old_node.name,
                rank=old_node.rank,
                parent_id=new_parent_id,
            )

            new_tree.add_node(new_node)

        # Copy relevant genomes
        for genome in self._genomes.values():
            if genome.tax_id in subtree_nodes:
                new_genome = GenomeInfo(
                    genome_id=genome.genome_id,
                    tax_id=id_mapping[genome.tax_id],
                    assembly_accession=genome.assembly_accession,
                    file_path=genome.file_path,
                    sequence_type=genome.sequence_type,
                    source=genome.source,
                )
                new_tree.add_genome(new_genome)

        return new_tree

    def graft_subtree(
        self,
        subtree: "TaxonomyTree",
        attachment_point: int,
        id_offset: Optional[int] = None,
    ) -> Dict[int, int]:
        """Graft a subtree onto this tree at the specified attachment point.

        Args:
            subtree: The TaxonomyTree to graft
            attachment_point: Tax ID where the subtree should be attached
            id_offset: Optional offset for reassigning tax_ids to avoid conflicts

        Returns:
            Dictionary mapping old tax_ids to new tax_ids in the grafted subtree
        """
        if attachment_point not in self._nodes:
            raise ValueError(f"Attachment point {attachment_point} does not exist")

        if not subtree._nodes:
            return {}

        # Find next available ID if no offset specified
        if id_offset is None:
            id_offset = max(self._nodes.keys()) + 1

        # Create ID mapping for the subtree
        id_mapping = {}
        sorted_subtree_ids = sorted(subtree._nodes.keys())

        for i, old_id in enumerate(sorted_subtree_ids):
            id_mapping[old_id] = id_offset + i

        # Ensure no conflicts
        while any(new_id in self._nodes for new_id in id_mapping.values()):
            id_offset += len(id_mapping)
            for i, old_id in enumerate(sorted_subtree_ids):
                id_mapping[old_id] = id_offset + i

        # Add nodes from subtree
        for old_node in subtree:
            new_id = id_mapping[old_node.tax_id]

            # Determine new parent: either attachment point (for root) or mapped parent
            if old_node.parent_id is None:
                new_parent_id = attachment_point
            else:
                new_parent_id = id_mapping[old_node.parent_id]

            new_node = TaxonomyNode(
                tax_id=new_id,
                name=old_node.name,
                rank=old_node.rank,
                parent_id=new_parent_id,
            )

            self.add_node(new_node)

        # Graft genomes
        for genome in subtree._genomes.values():
            if genome.tax_id in id_mapping:
                new_genome = GenomeInfo(
                    genome_id=genome.genome_id,
                    tax_id=id_mapping[genome.tax_id],
                    assembly_accession=genome.assembly_accession,
                    file_path=genome.file_path,
                    sequence_type=genome.sequence_type,
                    source=genome.source,
                )
                self.add_genome(new_genome)

        return id_mapping

    def merge_trees(
        self, other_tree: "TaxonomyTree", merge_strategy: str = "graft_at_root"
    ) -> Dict[int, int]:
        """Merge another tree into this one using the specified strategy.

        Args:
            other_tree: The TaxonomyTree to merge
            merge_strategy: Strategy for merging ('graft_at_root', 'merge_common_ancestors')

        Returns:
            Dictionary mapping old tax_ids from other_tree to new tax_ids in this tree
        """
        if merge_strategy == "graft_at_root":
            if self._root_id is None:
                raise ValueError("Cannot graft at root: this tree has no root")
            return self.graft_subtree(other_tree, self._root_id)

        elif merge_strategy == "merge_common_ancestors":
            # More sophisticated merging based on common node names/ranks
            id_mapping = {}

            # Find nodes with same names and ranks that could be merged
            common_nodes = []
            for other_node in other_tree:
                for our_node in self:
                    if (
                        other_node.name == our_node.name
                        and other_node.rank == our_node.rank
                    ):
                        common_nodes.append((other_node, our_node))
                        id_mapping[other_node.tax_id] = our_node.tax_id
                        break

            # Add remaining nodes that don't have matches
            id_offset = max(self._nodes.keys()) + 1 if self._nodes else 1

            for other_node in other_tree:
                if other_node.tax_id not in id_mapping:
                    # Find appropriate attachment point
                    attachment_point = self._root_id

                    if (
                        other_node.parent_id is not None
                        and other_node.parent_id in id_mapping
                    ):
                        attachment_point = id_mapping[other_node.parent_id]

                    new_id = id_offset
                    id_offset += 1

                    id_mapping[other_node.tax_id] = new_id

                    new_node = TaxonomyNode(
                        tax_id=new_id,
                        name=other_node.name,
                        rank=other_node.rank,
                        parent_id=attachment_point,
                    )

                    self.add_node(new_node)

            return id_mapping

        else:
            raise ValueError(f"Unknown merge strategy: {merge_strategy}")

    def compare_trees(self, other_tree: "TaxonomyTree") -> Dict[str, Any]:
        """Compare this tree with another tree and return structural differences.

        Args:
            other_tree: The TaxonomyTree to compare against

        Returns:
            Dictionary containing comparison results and differences
        """
        comparison: Dict[str, List[Any]] = {
            "nodes_only_in_self": [],
            "nodes_only_in_other": [],
            "nodes_in_both": [],
            "structural_differences": [],
            "rank_differences": [],
            "name_differences": [],
        }

        self_ids = set(self._nodes.keys())
        other_ids = set(other_tree._nodes.keys())

        # Find nodes unique to each tree
        comparison["nodes_only_in_self"] = list(self_ids - other_ids)
        comparison["nodes_only_in_other"] = list(other_ids - self_ids)
        comparison["nodes_in_both"] = list(self_ids & other_ids)

        # Compare nodes that exist in both trees
        for tax_id in comparison["nodes_in_both"]:
            self_node = self._nodes[tax_id]
            other_node = other_tree._nodes[tax_id]

            # Check for structural differences (different parents)
            if self_node.parent_id != other_node.parent_id:
                comparison["structural_differences"].append(
                    {
                        "tax_id": tax_id,
                        "self_parent": self_node.parent_id,
                        "other_parent": other_node.parent_id,
                    }
                )

            # Check for rank differences
            if self_node.rank != other_node.rank:
                comparison["rank_differences"].append(
                    {
                        "tax_id": tax_id,
                        "self_rank": self_node.rank.value,
                        "other_rank": other_node.rank.value,
                    }
                )

            # Check for name differences
            if self_node.name != other_node.name:
                comparison["name_differences"].append(
                    {
                        "tax_id": tax_id,
                        "self_name": self_node.name,
                        "other_name": other_node.name,
                    }
                )

        return comparison

    def get_tree_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the tree structure.

        Returns:
            Dictionary containing various tree statistics
        """
        stats: Dict[str, Any] = {
            "node_count": len(self._nodes),
            "genome_count": len(self._genomes),
            "max_depth": 0,
            "rank_distribution": {},
            "branching_factor_stats": {
                "max": 0,
                "min": float("inf"),
                "average": 0,
                "median": 0,
            },
            "leaf_node_count": 0,
            "internal_node_count": 0,
        }

        if not self._nodes:
            return stats

        branching_factors = []

        # Calculate statistics for each node
        for node in self._nodes.values():
            # Update rank distribution
            rank_name = node.rank.value
            rank_dist = stats["rank_distribution"]
            rank_dist[rank_name] = rank_dist.get(rank_name, 0) + 1

            # Calculate depth
            path = self.get_path_to_root(node.tax_id)
            depth = len(path) - 1  # Subtract 1 because root is at depth 0
            stats["max_depth"] = max(stats["max_depth"], depth)

            # Calculate branching factor
            children = self.get_children(node.tax_id)
            branching_factor = len(children)
            branching_factors.append(branching_factor)

            # Update leaf/internal node counts
            if branching_factor == 0:
                stats["leaf_node_count"] += 1
            else:
                stats["internal_node_count"] += 1

        # Calculate branching factor statistics
        if branching_factors:
            bf_stats = stats["branching_factor_stats"]
            bf_stats["max"] = max(branching_factors)
            bf_stats["min"] = min(branching_factors)  # Include leaf nodes (0 children)
            bf_stats["average"] = sum(branching_factors) / len(branching_factors)

            sorted_factors = sorted(branching_factors)
            n = len(sorted_factors)
            stats["branching_factor_stats"]["median"] = (
                sorted_factors[n // 2]
                if n % 2 == 1
                else (sorted_factors[n // 2 - 1] + sorted_factors[n // 2]) / 2
            )

        return stats

    def purge_nodes_without_genomes(self, require_fasta_files: bool = True, force: bool = False) -> Dict[str, Any]:
        """Remove nodes that don't have genomes with FASTA files, keeping essential lineages.
        
        This method implements the purge_database functionality by:
        1. Identifying all nodes with genomes that have FASTA files (if required)
        2. Finding all lineages from these nodes to the root
        3. Removing all other nodes not in these essential lineages
        
        Args:
            require_fasta_files: If True, only keep nodes with genomes that have file_path.
                                If False, keep nodes with any genome data.
            force: If True, bypass safety checks that prevent excessive purging.
        
        Returns:
            Dictionary with purge statistics including nodes removed and kept
        """
        if not self._nodes:
            return {
                "nodes_before": 0,
                "nodes_after": 0,
                "nodes_removed": 0,
                "genomes_retained": 0,
                "lineages_preserved": 0,
            }
        
        initial_node_count = len(self._nodes)
        
        # Step 1: Find all nodes with eligible genomes
        nodes_with_genomes = set()
        eligible_genomes = []
        
        for genome in self._genomes.values():
            # Skip genomes that point to non-existent nodes
            if genome.tax_id not in self._nodes:
                continue
                
            # Check if genome meets the criteria
            has_file = genome.file_path is not None and str(genome.file_path).strip() != ""
            
            if not require_fasta_files or has_file:
                nodes_with_genomes.add(genome.tax_id)
                eligible_genomes.append(genome)
        
        if not nodes_with_genomes:
            # No eligible nodes found - this would remove everything
            # Return stats without making changes
            return {
                "nodes_before": initial_node_count,
                "nodes_after": initial_node_count,
                "nodes_removed": 0,
                "genomes_retained": 0,
                "lineages_preserved": 0,
                "warning": "No nodes with eligible genomes found - no changes made"
            }
        
        # Safety check: prevent excessive purging (more than 95% of nodes)
        temp_essential_nodes = set()
        for node_id in nodes_with_genomes:
            path = self.get_path_to_root(node_id)
            temp_essential_nodes.update([n.tax_id for n in path])
        
        potential_removal_count = initial_node_count - len(temp_essential_nodes)
        if potential_removal_count > 0 and not force:
            removal_percentage = (potential_removal_count / initial_node_count) * 100
            if removal_percentage > 95.0:
                return {
                    "nodes_before": initial_node_count,
                    "nodes_after": initial_node_count,
                    "nodes_removed": 0,
                    "genomes_retained": len(eligible_genomes),
                    "lineages_preserved": 0,
                    "warning": f"Purge would remove {removal_percentage:.1f}% of nodes - operation blocked for safety. Use --force in CLI if intended."
                }
        
        # Step 2: Find all lineages from genome nodes to root
        essential_nodes = set()
        lineages_count = 0
        
        for node_id in nodes_with_genomes:
            lineages_count += 1
            # Get path from node to root
            path = self.get_path_to_root(node_id)
            essential_nodes.update([n.tax_id for n in path])
        
        # Step 3: Identify nodes to remove
        all_node_ids = set(self._nodes.keys())
        nodes_to_remove = all_node_ids - essential_nodes
        
        # Step 4: Remove non-essential nodes
        # Sort nodes by depth (deepest first to avoid parent-child dependency issues)
        nodes_by_depth = []
        for node_id in nodes_to_remove:
            try:
                path = self.get_path_to_root(node_id)
                depth = len(path) - 1
                nodes_by_depth.append((depth, node_id))
            except:
                # If path calculation fails, remove this node last
                nodes_by_depth.append((999, node_id))
        
        # Sort by depth in descending order (deepest first)
        nodes_by_depth.sort(reverse=True)
        
        removed_count = 0
        for depth, node_id in nodes_by_depth:
            if node_id in self._nodes:  # Node might have been removed as child of another
                try:
                    # Remove node and reassign children to parent
                    self.remove_node(node_id, reassign_children=True)
                    removed_count += 1
                except ValueError:
                    # Node might already be removed or have issues
                    continue
        
        # Step 5: Clean up genomes that belong to removed nodes or point to non-existent nodes
        remaining_genomes = {}
        for genome_id, genome in self._genomes.items():
            if genome.tax_id in essential_nodes and genome.tax_id in self._nodes:
                remaining_genomes[genome_id] = genome
        
        self._genomes = remaining_genomes
        
        final_node_count = len(self._nodes)
        
        return {
            "nodes_before": initial_node_count,
            "nodes_after": final_node_count,
            "nodes_removed": removed_count,
            "genomes_retained": len(eligible_genomes),
            "lineages_preserved": lineages_count,
            "nodes_with_genomes": len(nodes_with_genomes),
            "essential_nodes_kept": len(essential_nodes),
        }


# Phase 4: Enhanced data models for accession-based architecture

from datetime import datetime


@dataclass(frozen=True)
class EnhancedGenomeInfo:
    """Enhanced genome information for Phase 4 accession-based architecture.
    
    This model replaces GenomeInfo for the new genomes_v2 table and provides
    comprehensive accession tracking without SRA support.
    """

    genome_id: str
    tax_id: int
    assembly_accession: Optional[str] = None     # GCF_/GCA_ (RefSeq/GenBank)
    nucleotide_accession: Optional[str] = None   # NC_/NZ_/CP_ (chromosome/contig)
    biosample_accession: Optional[str] = None    # SAMN_/SAMD_/SAME_ (sample)
    
    # File management
    file_path: Optional[str] = None              # Path to genome FASTA file
    file_exists: bool = False                    # Current file existence status
    file_checksum: Optional[str] = None          # SHA256 for integrity
    file_size: Optional[int] = None
    last_validated: Optional[datetime] = None    # Last validation timestamp
    
    # Metadata
    sequence_count: Optional[int] = None         # Number of contigs/chromosomes
    total_length: Optional[int] = None           # Total genome size in bp
    strain: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None                 # NCBI/GTDB/SILVA/custom
    download_date: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate enhanced genome info after initialization."""
        if not self.genome_id.strip():
            raise ValueError("Genome ID cannot be empty")
        if self.tax_id <= 0:
            raise ValueError(f"Tax ID must be positive, got {self.tax_id}")

    @property
    def primary_accession(self) -> Optional[str]:
        """Get the primary accession for this genome (assembly > nucleotide)."""
        return self.assembly_accession or self.nucleotide_accession

    def validate(self) -> List[str]:
        """Validate enhanced genome information."""
        issues = []

        if not self.genome_id:
            issues.append("Genome ID cannot be empty")
        if self.tax_id <= 0:
            issues.append("Taxonomy ID must be positive")

        # File validation
        if self.file_path:
            from pathlib import Path
            path = Path(self.file_path)
            if not path.exists():
                issues.append(f"Genome file does not exist: {self.file_path}")
            elif not path.is_file():
                issues.append(f"Path is not a file: {self.file_path}")

        # Accession validation
        if self.assembly_accession and not self._validate_assembly_accession(self.assembly_accession):
            issues.append(f"Invalid assembly accession format: {self.assembly_accession}")
        if self.nucleotide_accession and not self._validate_nucleotide_accession(self.nucleotide_accession):
            issues.append(f"Invalid nucleotide accession format: {self.nucleotide_accession}")
        if self.biosample_accession and not self._validate_biosample_accession(self.biosample_accession):
            issues.append(f"Invalid biosample accession format: {self.biosample_accession}")

        return issues

    @staticmethod
    def _validate_assembly_accession(accession: str) -> bool:
        """Validate assembly accession format (GCF_/GCA_)."""
        import re
        return bool(re.match(r'^GC[FA]_\d{9}\.\d+$', accession))

    @staticmethod
    def _validate_nucleotide_accession(accession: str) -> bool:
        """Validate nucleotide accession format."""
        import re
        return bool(re.match(r'^(NC|NZ|CP|AP|AE|AL|AM|BA|BX|CM|FO|FP|FQ|FR)_\d+\.\d+$', accession))

    @staticmethod
    def _validate_biosample_accession(accession: str) -> bool:
        """Validate biosample accession format."""
        import re
        return bool(re.match(r'^SAM[NDE]\d+$', accession))


@dataclass(frozen=True)
class ProteinInfo:
    """Information about individual proteins associated with genomes.
    
    Note: This tracks protein metadata only. Individual protein files are not tracked -
    instead, proteins are organized into collection files (taxa-specific or global).
    """

    protein_id: str                               # Unique protein identifier
    tax_id: int
    genome_id: Optional[str] = None              # Link to parent genome
    protein_accession: Optional[str] = None      # WP_/YP_/NP_ accession
    gene_name: Optional[str] = None              # Gene name/locus tag
    
    # Protein metadata only (no individual file paths)
    sequence_length: Optional[int] = None        # Protein length in amino acids
    product: Optional[str] = None                # Protein product description
    ec_number: Optional[str] = None              # Enzyme commission number
    go_terms: Optional[str] = None               # Gene ontology terms (JSON)

    def __post_init__(self) -> None:
        """Validate protein info after initialization."""
        if not self.protein_id.strip():
            raise ValueError("Protein ID cannot be empty")
        if self.tax_id <= 0:
            raise ValueError(f"Tax ID must be positive, got {self.tax_id}")

    def validate(self) -> List[str]:
        """Validate protein information."""
        issues = []

        if not self.protein_id:
            issues.append("Protein ID cannot be empty")
        if self.tax_id <= 0:
            issues.append("Taxonomy ID must be positive")

        # Protein accession validation
        if self.protein_accession and not self._validate_protein_accession(self.protein_accession):
            issues.append(f"Invalid protein accession format: {self.protein_accession}")

        return issues

    @staticmethod
    def _validate_protein_accession(accession: str) -> bool:
        """Validate protein accession format."""
        import re
        return bool(re.match(r'^(WP|YP|NP|XP|AP)_\d+\.\d+$', accession))


@dataclass(frozen=True)
class SequenceFile:
    """Information about sequence files that can contain multiple taxa/sequences.
    
    This model tracks files containing sequences (genomes or proteins) and supports
    flexible file organization strategies.
    """

    file_id: Optional[int] = None                # Auto-generated
    file_path: str = ""                          # Path to sequence file
    file_type: str = ""                          # 'genome', 'protein_taxa', 'protein_global'
    scope: str = ""                              # 'single_taxa', 'multi_taxa', 'global'
    taxa_count: int = 1                          # Number of taxa in file
    sequence_count: Optional[int] = None         # Total sequences in file
    
    # File management
    file_exists: bool = False
    file_checksum: Optional[str] = None
    file_size: Optional[int] = None
    last_validated: Optional[datetime] = None
    created_date: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate sequence file info after initialization."""
        if not self.file_path.strip():
            raise ValueError("File path cannot be empty")
        if self.file_type not in ['genome', 'protein_taxa', 'protein_global']:
            raise ValueError(f"Invalid file type: {self.file_type}")
        if self.scope not in ['single_taxa', 'multi_taxa', 'global']:
            raise ValueError(f"Invalid scope: {self.scope}")


@dataclass(frozen=True)
class AccessionMapping:
    """Mapping between accessions and taxonomy IDs.
    
    This model supports the accession2taxid functionality without SRA support.
    """

    accession: str                               # Primary accession
    accession_version: Optional[str] = None      # Versioned accession
    tax_id: int = 0
    accession_type: Optional[str] = None         # 'assembly'/'nucleotide'/'protein'

    def __post_init__(self) -> None:
        """Validate accession mapping after initialization."""
        if not self.accession.strip():
            raise ValueError("Accession cannot be empty")
        if self.tax_id <= 0:
            raise ValueError(f"Tax ID must be positive, got {self.tax_id}")
        if self.accession_type and self.accession_type not in ['assembly', 'nucleotide', 'protein']:
            raise ValueError(f"Invalid accession type: {self.accession_type}")

    def validate(self) -> List[str]:
        """Validate accession mapping."""
        issues = []

        if not self.accession:
            issues.append("Accession cannot be empty")
        if self.tax_id <= 0:
            issues.append("Taxonomy ID must be positive")

        return issues


@dataclass
class FileRegistryEntry:
    """Registry entry for tracking and validating sequence files.
    
    This model supports file tracking, validation, and repair operations.
    """

    file_id: Optional[int] = None                # Auto-generated
    file_path: str = ""                          # Path to file
    file_type: str = ""                          # 'genome'/'protein_taxa'/'protein_global'
    entity_id: str = ""                          # genome_id or tax_id or 'global'
    tax_id: Optional[int] = None                 # NULL for global protein db
    
    # File status
    expected_path: Optional[str] = None          # Original/expected path
    actual_path: Optional[str] = None            # Current actual path (if moved)
    exists: bool = False
    accessible: bool = False
    valid_format: bool = False
    
    # File metadata
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    last_checked: Optional[datetime] = None
    
    # Issues tracking
    issue_type: Optional[str] = None             # 'missing'/'moved'/'corrupted'/'inaccessible'
    issue_description: Optional[str] = None
    repair_attempted: bool = False
    repair_date: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate registry entry after initialization."""
        if not self.file_path.strip():
            raise ValueError("File path cannot be empty")
        if not self.entity_id.strip():
            raise ValueError("Entity ID cannot be empty")
        if self.file_type not in ['genome', 'protein_taxa', 'protein_global']:
            raise ValueError(f"Invalid file type: {self.file_type}")

    def validate(self) -> List[str]:
        """Validate registry entry."""
        issues = []

        if not self.file_path:
            issues.append("File path cannot be empty")
        if not self.entity_id:
            issues.append("Entity ID cannot be empty")

        return issues
