"""Visualize command for displaying taxonomy trees."""

import argparse
from typing import Optional, Dict, Any, List, Set, Union
from pathlib import Path

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError
from ...core.models import TaxonomyNode
from ...database.sqlite import SQLiteTaxonomyRepository
from ...core.models import TaxonomyTree


class VisualizeCommand(BaseCommand):
    """Command to visualize taxonomy databases as trees."""
    
    @classmethod
    def register_parser(cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> argparse.ArgumentParser:
        """Register the visualize command parser."""
        parser = subparsers.add_parser(
            'visualize',
            help='Visualize taxonomy database as tree',
            description='Display taxonomy database structure as hierarchical tree',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Show full tree from root
  flextaxd visualize --database my_db.ftd --type tree
  
  # Limit tree depth
  flextaxd visualize --database my_db.ftd --type tree --max-depth 3
  
  # Start from specific node
  flextaxd visualize --database my_db.ftd --type tree --start-node "Bacteria" --max-depth 2
  
  # Show tree with genome counts
  flextaxd visualize --database my_db.ftd --type tree --show-genomes
  
  # Compact view with node IDs
  flextaxd visualize --database my_db.ftd --type tree --show-ids --compact
            """
        )
        
        parser.add_argument(
            '--database', '-d',
            type=str,
            required=True,
            help='Database file path (.ftd)'
        )
        
        parser.add_argument(
            '--type', '-t',
            choices=['tree', 'summary', 'newick', 'newick_vis', 'plot'],
            default='tree',
            help='Visualization type: tree=ASCII tree, newick=raw format, newick_vis=BioPython ASCII, plot=graphical plot (default: tree)'
        )
        
        parser.add_argument(
            '--start-node',
            type=str,
            default='root',
            help='Starting node name or ID (default: root)'
        )
        
        parser.add_argument(
            '--max-depth',
            type=int,
            default=0,
            help='Maximum depth to display (0 = unlimited, default: 0)'
        )
        
        parser.add_argument(
            '--show-ids',
            action='store_true',
            help='Show node taxonomy IDs'
        )
        
        parser.add_argument(
            '--show-genomes',
            action='store_true',
            help='Show genome counts for each node'
        )
        
        parser.add_argument(
            '--show-ranks',
            action='store_true',
            help='Show taxonomic ranks'
        )
        
        parser.add_argument(
            '--compact',
            action='store_true',
            help='Use compact tree display'
        )
        
        parser.add_argument(
            '--format',
            choices=['text', 'json'],
            default='text',
            help='Output format (default: text)'
        )
        
        # Advanced visualization options (legacy compatibility)
        parser.add_argument(
            '--label-size',
            type=int,
            default=0,
            help='Size of labels in graphical plots (0=auto, legacy: --vis_label_size)'
        )
        
        parser.add_argument(
            '--clip-labels',
            action='store_true',
            help='Clip long node names in tree visualization (legacy: --vis_clip_labels)'
        )
        
        parser.add_argument(
            '--save-plot',
            type=str,
            help='Save graphical plot to file (e.g., tree.png, tree.pdf)'
        )
        
        return parser
    
    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the visualize command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)
            
            # Load database and tree
            with SQLiteTaxonomyRepository(args.database) as repository:
                tree = repository.load_tree()
                
                self.logger.info(f"Loaded tree with {tree.node_count} nodes")
                
                if args.type == 'tree':
                    self._visualize_tree(tree, args)
                elif args.type == 'summary':
                    self._visualize_summary(tree, args)
                elif args.type == 'newick':
                    self._visualize_newick(tree, args)
                elif args.type == 'newick_vis':
                    self._visualize_newick_ascii(tree, args)
                elif args.type == 'plot':
                    self._visualize_plot(tree, args)
                
            return 0
            
        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1
            
        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1
    
    def _visualize_tree(self, tree: TaxonomyTree, args: argparse.Namespace) -> None:
        """Visualize taxonomy tree structure."""
        # Find starting node
        start_node = self._find_start_node(tree, args.start_node)
        if not start_node:
            raise ValidationError(f"Start node '{args.start_node}' not found")
        
        if args.format == 'json':
            self._output_tree_json(tree, start_node, args)
        else:
            self._output_tree_text(tree, start_node, args)
    
    def _visualize_summary(self, tree: TaxonomyTree, args: argparse.Namespace) -> None:
        """Visualize tree summary with key statistics."""
        # Find starting node
        start_node = self._find_start_node(tree, args.start_node)
        if not start_node:
            raise ValidationError(f"Start node '{args.start_node}' not found")
        
        if args.format == 'json':
            self._output_summary_json(tree, start_node, args)
        else:
            self._output_summary_text(tree, start_node, args)
    
    def _find_start_node(self, tree: TaxonomyTree, start_identifier: str) -> Optional[TaxonomyNode]:
        """Find starting node by name or ID."""
        # Try as taxonomy ID first
        try:
            tax_id = int(start_identifier)
            node = tree.get_node(tax_id)
            if node:
                return node
        except ValueError:
            pass
        
        # Try as node name
        for node in tree:
            if node.name.lower() == start_identifier.lower():
                return node
            # Also try exact match
            if node.name == start_identifier:
                return node
        
        # Special case for 'root' - find the actual root node
        if start_identifier.lower() == 'root':
            if tree.root_id is not None:
                return tree.get_node(tree.root_id)
            # If no explicit root, find nodes with no parents
            for node in tree:
                if node.parent_id is None:
                    return node
        
        return None
    
    def _output_tree_text(self, tree: TaxonomyTree, start_node: TaxonomyNode, args: argparse.Namespace) -> None:
        """Output tree in text format."""
        print(f"Taxonomy Tree Visualization")
        print(f"{'=' * 50}")
        print(f"Starting from: {start_node.name}")
        if args.max_depth > 0:
            print(f"Maximum depth: {args.max_depth}")
        print()
        
        self._print_tree_node(tree, start_node, args, depth=0, is_last_sibling=[])
    
    def _print_tree_node(self, tree: TaxonomyTree, node: TaxonomyNode, args: argparse.Namespace, 
                         depth: int, is_last_sibling: List[bool]) -> None:
        """Recursively print tree nodes."""
        # Check depth limit
        if args.max_depth > 0 and depth >= args.max_depth:
            return
        
        # Build tree prefix
        prefix = ""
        for i, is_last in enumerate(is_last_sibling[:-1]):
            if is_last:
                prefix += "    "
            else:
                prefix += "│   "
        
        if depth > 0:
            if is_last_sibling[-1]:
                prefix += "└── "
            else:
                prefix += "├── "
        
        # Build node display
        node_display = node.name
        
        if args.show_ids:
            node_display += f" ({node.tax_id})"
        
        if args.show_ranks and node.rank:
            node_display += f" [{node.rank.value}]"
        
        if args.show_genomes:
            genome_count = len(tree.get_genomes_for_node(node.tax_id))
            if genome_count > 0:
                node_display += f" 🧬{genome_count}"
        
        print(f"{prefix}{node_display}")
        
        # Get and sort children
        children = tree.get_children(node.tax_id)
        if not children:
            return
        
        children_nodes: List[TaxonomyNode] = []
        for child_id in children:
            child_node = tree.get_node(child_id)
            if child_node is not None:
                children_nodes.append(child_node)
        
        # Sort children by name
        children_nodes.sort(key=lambda n: n.name)
        
        # Print children
        for i, child in enumerate(children_nodes):
            is_last = (i == len(children_nodes) - 1)
            new_is_last_sibling = is_last_sibling + [is_last]
            self._print_tree_node(tree, child, args, depth + 1, new_is_last_sibling)
    
    def _output_tree_json(self, tree: TaxonomyTree, start_node: TaxonomyNode, args: argparse.Namespace) -> None:
        """Output tree in JSON format."""
        import json
        
        def build_tree_dict(node: TaxonomyNode, current_depth: int = 0) -> Dict[str, Any]:
            """Build tree dictionary recursively."""
            node_dict = {
                'name': node.name,
                'tax_id': node.tax_id,
                'rank': node.rank.value if node.rank else None,
                'depth': current_depth
            }
            
            if args.show_genomes:
                genome_count = len(tree.get_genomes_for_node(node.tax_id))
                node_dict['genome_count'] = genome_count
            
            # Add children if within depth limit
            if args.max_depth == 0 or current_depth < args.max_depth:
                children = tree.get_children(node.tax_id)
                if children:
                    children_nodes: List[TaxonomyNode] = []
                    for child_id in children:
                        child_node = tree.get_node(child_id)
                        if child_node is not None:
                            children_nodes.append(child_node)
                    children_nodes.sort(key=lambda n: n.name)
                    
                    node_dict['children'] = [
                        build_tree_dict(child, current_depth + 1) 
                        for child in children_nodes
                    ]
            
            return node_dict
        
        tree_data = {
            'metadata': {
                'start_node': start_node.name,
                'start_node_id': start_node.tax_id,
                'max_depth': args.max_depth,
                'total_nodes_in_tree': tree.node_count
            },
            'tree': build_tree_dict(start_node)
        }
        
        print(json.dumps(tree_data, indent=2))
    
    def _output_summary_text(self, tree: TaxonomyTree, start_node: TaxonomyNode, args: argparse.Namespace) -> None:
        """Output summary in text format."""
        # Count nodes in subtree
        subtree_nodes = self._count_subtree_nodes(tree, start_node, args.max_depth)
        
        print(f"Taxonomy Tree Summary")
        print(f"{'=' * 40}")
        print(f"Starting node: {start_node.name} (ID: {start_node.tax_id})")
        if start_node.rank:
            print(f"Starting rank: {start_node.rank.value}")
        print(f"Subtree nodes: {subtree_nodes}")
        
        if args.show_genomes:
            total_genomes = self._count_subtree_genomes(tree, start_node, args.max_depth)
            print(f"Total genomes: {total_genomes}")
        
        print()
        
        # Show rank distribution in subtree
        rank_counts = self._get_subtree_rank_distribution(tree, start_node, args.max_depth)
        if rank_counts:
            print("Rank Distribution:")
            print("-" * 20)
            for rank, count in sorted(rank_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {rank}: {count}")
    
    def _output_summary_json(self, tree: TaxonomyTree, start_node: TaxonomyNode, args: argparse.Namespace) -> None:
        """Output summary in JSON format."""
        import json
        
        subtree_nodes = self._count_subtree_nodes(tree, start_node, args.max_depth)
        rank_counts = self._get_subtree_rank_distribution(tree, start_node, args.max_depth)
        
        summary_data = {
            'start_node': {
                'name': start_node.name,
                'tax_id': start_node.tax_id,
                'rank': start_node.rank.value if start_node.rank else None
            },
            'subtree_stats': {
                'node_count': subtree_nodes,
                'max_depth_analyzed': args.max_depth
            },
            'rank_distribution': rank_counts
        }
        
        if args.show_genomes:
            total_genomes = self._count_subtree_genomes(tree, start_node, args.max_depth)
            summary_data['subtree_stats']['genome_count'] = total_genomes
        
        print(json.dumps(summary_data, indent=2))
    
    def _count_subtree_nodes(self, tree: TaxonomyTree, node: TaxonomyNode, max_depth: int, current_depth: int = 0) -> int:
        """Count nodes in subtree."""
        if max_depth > 0 and current_depth >= max_depth:
            return 0
        
        count = 1  # Count current node
        
        children = tree.get_children(node.tax_id)
        for child_id in children:
            child = tree.get_node(child_id)
            if child:
                count += self._count_subtree_nodes(tree, child, max_depth, current_depth + 1)
        
        return count
    
    def _count_subtree_genomes(self, tree: TaxonomyTree, node: TaxonomyNode, max_depth: int, current_depth: int = 0) -> int:
        """Count genomes in subtree."""
        if max_depth > 0 and current_depth >= max_depth:
            return 0
        
        count = len(tree.get_genomes_for_node(node.tax_id))
        
        children = tree.get_children(node.tax_id)
        for child_id in children:
            child = tree.get_node(child_id)
            if child:
                count += self._count_subtree_genomes(tree, child, max_depth, current_depth + 1)
        
        return count
    
    def _get_subtree_rank_distribution(self, tree: TaxonomyTree, node: TaxonomyNode, max_depth: int, 
                                     current_depth: int = 0) -> Dict[str, int]:
        """Get rank distribution in subtree."""
        if max_depth > 0 and current_depth >= max_depth:
            return {}
        
        ranks: Dict[str, int] = {}
        
        # Count current node
        rank_name = node.rank.value if node.rank else 'unknown'
        ranks[rank_name] = ranks.get(rank_name, 0) + 1
        
        # Count children
        children = tree.get_children(node.tax_id)
        for child_id in children:
            child = tree.get_node(child_id)
            if child:
                child_ranks = self._get_subtree_rank_distribution(tree, child, max_depth, current_depth + 1)
                for rank, count in child_ranks.items():
                    ranks[rank] = ranks.get(rank, 0) + count
        
        return ranks
    
    def _visualize_newick(self, tree: TaxonomyTree, args: argparse.Namespace) -> None:
        """Output tree in Newick format."""
        # Find starting node
        start_node = self._find_start_node(tree, args.start_node)
        if not start_node:
            raise ValidationError(f"Start node '{args.start_node}' not found")
        
        # Generate Newick string
        newick_string = self._generate_newick_string(tree, start_node, args.max_depth)
        # Add proper Newick termination
        if not newick_string.endswith(';'):
            newick_string += ';'
        print(newick_string)
    
    def _visualize_newick_ascii(self, tree: TaxonomyTree, args: argparse.Namespace) -> None:
        """Output tree using BioPython ASCII visualization."""
        try:
            from Bio import Phylo
            from io import StringIO
        except ImportError:
            raise ValidationError("BioPython is required for newick_vis visualization. Install with: pip install biopython")
        
        # Find starting node
        start_node = self._find_start_node(tree, args.start_node)
        if not start_node:
            raise ValidationError(f"Start node '{args.start_node}' not found")
        
        # Generate Newick string and parse with BioPython
        newick_string = self._generate_newick_string(tree, start_node, args.max_depth)
        # Add proper Newick termination
        if not newick_string.endswith(';'):
            newick_string += ';'
        
        try:
            phylo_tree = Phylo.read(StringIO(newick_string), "newick")  # type: ignore
            
            print(f"BioPython ASCII Tree Visualization")
            print(f"{'=' * 50}")
            print(f"Starting from: {start_node.name}")
            if args.max_depth > 0:
                print(f"Maximum depth: {args.max_depth}")
            print()
            
            # Use BioPython's ASCII drawing
            Phylo.draw_ascii(phylo_tree)  # type: ignore
            
        except Exception as e:
            raise ValidationError(f"Error parsing Newick tree with BioPython: {e}")
    
    def _visualize_plot(self, tree: TaxonomyTree, args: argparse.Namespace) -> None:
        """Create graphical plot using matplotlib and BioPython."""
        try:
            from Bio import Phylo
            from io import StringIO
            import matplotlib
            # Use non-interactive backend to avoid GUI requirements
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import pylab
        except ImportError as e:
            missing_dep = "biopython" if "Bio" in str(e) else "matplotlib"
            raise ValidationError(f"{missing_dep} is required for plot visualization. Install with: pip install {missing_dep}")
        
        # Find starting node
        start_node = self._find_start_node(tree, args.start_node)
        if not start_node:
            raise ValidationError(f"Start node '{args.start_node}' not found")
        
        # Generate Newick string and parse with BioPython
        newick_string = self._generate_newick_string(tree, start_node, args.max_depth)
        # Add proper Newick termination
        if not newick_string.endswith(';'):
            newick_string += ';'
        
        try:
            phylo_tree = Phylo.read(StringIO(newick_string), "newick")  # type: ignore
            
            # Set up the plot
            plt.figure(figsize=(12, 8))
            
            # Customize label function
            def label_func(node: Any) -> str:
                if not node.name:
                    return ""
                name = node.name
                
                # Clip labels if requested
                if args.clip_labels and len(name) > 20:
                    name = name[:17] + "..."
                    
                return str(name)
            
            # Set font size for labels if specified
            if args.label_size > 0:
                import matplotlib
                matplotlib.rcParams['font.size'] = args.label_size
            
            # Create the plot
            ax = plt.gca()  # Get current axes
            Phylo.draw(phylo_tree,  # type: ignore
                      label_func=label_func,
                      do_show=False,
                      axes=ax)
            
            # Remove frame (spines) but keep x and y axes
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['bottom'].set_visible(True)
            ax.spines['left'].set_visible(True)
            
            # Extend x-axis to accommodate label text
            xlim = ax.get_xlim()
            # Calculate maximum label length for padding
            max_label_length = 0
            for node in phylo_tree.find_clades():
                if node.name:
                    display_name = label_func(node)
                    max_label_length = max(max_label_length, len(display_name))
            
            # Extend x-axis based on label length (approximate character width)
            padding = max_label_length * 0.01  # Adjust multiplier as needed
            ax.set_xlim(xlim[0], xlim[1] + padding)
            
            # Set title
            plt.title(f"Taxonomy Tree - Starting from: {start_node.name}", fontsize=14, fontweight='bold')
            plt.tight_layout()
            
            # Save or display
            output_file = args.save_plot if args.save_plot else "flextaxd_tree_plot.png"
            
            # Ensure we have an extension
            if not any(output_file.endswith(ext) for ext in ['.png', '.pdf', '.svg', '.jpg', '.jpeg']):
                output_file += '.png'
            
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            
            print(f"Tree plot saved to: {output_file}")
            print(f"Starting node: {start_node.name}")
            if args.max_depth > 0:
                print(f"Maximum depth: {args.max_depth}")
            
        except Exception as e:
            raise ValidationError(f"Error creating tree plot: {e}")
    
    def _generate_newick_string(self, tree: TaxonomyTree, start_node: TaxonomyNode, max_depth: int, current_depth: int = 0) -> str:
        """Generate Newick format string for a subtree."""
        # Check depth limit
        if max_depth > 0 and current_depth >= max_depth:
            return start_node.name.replace(' ', '_').replace('(', '_').replace(')', '_').replace(',', '_').replace(';', '_').replace(':', '_')
        
        # Get children
        children = tree.get_children(start_node.tax_id)
        
        if not children:
            # Leaf node
            node_name = start_node.name.replace(' ', '_').replace('(', '_').replace(')', '_').replace(',', '_').replace(';', '_').replace(':', '_')
            return node_name
        
        # Internal node with children
        child_strings = []
        for child_id in children:
            child_node = tree.get_node(child_id)
            if child_node:
                child_newick = self._generate_newick_string(tree, child_node, max_depth, current_depth + 1)
                child_strings.append(child_newick)
        
        # Sort children for consistent output
        child_strings.sort()
        
        # Build Newick string
        node_name = start_node.name.replace(' ', '_').replace('(', '_').replace(')', '_').replace(',', '_').replace(';', '_').replace(':', '_')
        
        if child_strings:
            children_str = ','.join(child_strings)
            return f"({children_str}){node_name}"
        else:
            return node_name