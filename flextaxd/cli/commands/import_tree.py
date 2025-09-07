"""Import-tree command for importing taxonomy trees from files."""

import argparse
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError
from ...core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from ...database.sqlite import SQLiteTaxonomyRepository


class ImportTreeCommand(BaseCommand):
    """Command to import taxonomy trees from files with flexible integration strategies."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the import-tree command parser."""
        parser = subparsers.add_parser(
            "import-tree",
            help="Import taxonomy tree from file",
            description="Import a taxonomy tree from a file with flexible integration strategies",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Merge new nodes into existing tree (skip duplicates)
  flextaxd import-tree --database my_db.ftd --input tree.tsv --attach-to "Escherichia coli" --strategy merge
  
  # Replace an existing node with imported tree
  flextaxd import-tree --database my_db.ftd --input tree.tsv --target "Old Node" --strategy replace --keep-names file
  
  # Attach tree as child of existing node
  flextaxd import-tree --database my_db.ftd --input tree.tsv --root-node "Francisella tularensis" --attach-to "Francisella" --strategy merge
  
  # Preview changes before making them
  flextaxd import-tree --database my_db.ftd --input tree.tsv --attach-to "Parent" --strategy merge --dry-run
  
  # Force replacement with detailed control
  flextaxd import-tree --database my_db.ftd --input tree.tsv --target "Exact Node Name" --strategy replace --keep-names database --force
            """,
        )

        # Required arguments
        parser.add_argument(
            "--database", "-d", type=str, required=True,
            help="Database file path (.ftd)"
        )

        parser.add_argument(
            "--input", "-i", type=str, required=True,
            help="Input tree file (TSV format)"
        )

        # Integration strategy
        parser.add_argument(
            "--strategy", choices=["merge", "replace"], default="merge",
            help="Integration strategy: merge (add new nodes), replace (replace existing node)"
        )

        # Attachment point (where to connect the imported tree)
        attach_group = parser.add_mutually_exclusive_group()
        attach_group.add_argument(
            "--attach-to", type=str,
            help="Attach imported tree to this existing node (by name)"
        )
        attach_group.add_argument(
            "--attach-to-id", type=int,
            help="Attach imported tree to this existing node (by tax_id)"
        )
        attach_group.add_argument(
            "--target", type=str,
            help="Specific node to replace (more precise than --attach-to, requires --strategy replace)"
        )

        # Root specification in imported file
        parser.add_argument(
            "--root-node", type=str,
            help="Specify which node in the input file should be the attachment point"
        )

        parser.add_argument(
            "--auto-root", action="store_true", default=True,
            help="Automatically detect root node in input file (default: True)"
        )

        # Name handling for replace strategy
        parser.add_argument(
            "--keep-names", choices=["database", "file", "prompt"], default="file",
            help="Which names to keep when replacing nodes (default: file)"
        )

        # Conflict resolution
        parser.add_argument(
            "--on-conflict", choices=["skip", "update", "error"], default="skip",
            help="What to do when nodes already exist (default: skip)"
        )

        # Format specification
        parser.add_argument(
            "--format", choices=["auto", "tsv"], default="auto",
            help="Input file format (default: auto-detect)"
        )

        # Options
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Preview changes without making them"
        )

        parser.add_argument(
            "--force", action="store_true",
            help="Force operation even with warnings"
        )

        parser.add_argument(
            "--backup", action="store_true", default=True,
            help="Create backup before major changes (default: True)"
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the import-tree command."""
        try:
            # Validate inputs
            self._validate_database_path(args.database, must_exist=True)
            self._validate_input_file(args.input)
            self._validate_strategy_requirements(args)

            # Load input tree
            input_tree = self._load_input_tree(args.input, args.format)
            self.logger.info(f"Loaded input tree with {input_tree.node_count} nodes")
            

            with SQLiteTaxonomyRepository(args.database) as repository:
                # Determine attachment strategy
                attachment_info = self._determine_attachment_strategy(repository, input_tree, args)
                
                if args.dry_run:
                    return self._preview_import(repository, input_tree, attachment_info, args)
                else:
                    return self._execute_import(repository, input_tree, attachment_info, args)

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"❌ Error: {e.message}")
            return 1

        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"❌ Database error: {e.message}")
            return 1

        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            print(f"❌ Error: {e}")
            return 1

    def _validate_input_file(self, input_path: str) -> None:
        """Validate input file exists and is readable."""
        file_path = Path(input_path)
        if not file_path.exists():
            raise ValidationError(f"Input file not found: {input_path}")
        if not file_path.is_file():
            raise ValidationError(f"Input path is not a file: {input_path}")

    def _validate_strategy_requirements(self, args: argparse.Namespace) -> None:
        """Validate that strategy and parameters are compatible."""
        if args.strategy == "replace":
            if not args.target and not args.attach_to and not args.attach_to_id:
                raise ValidationError("Replace strategy requires --target, --attach-to, or --attach-to-id")
        
        if args.target and args.strategy != "replace":
            raise ValidationError("--target can only be used with --strategy replace")

        if args.keep_names != "file" and args.strategy != "replace":
            self.logger.warning("--keep-names is only relevant for replace strategy")

    def _load_input_tree(self, input_path: str, format_type: str) -> TaxonomyTree:
        """Load taxonomy tree from input file."""
        from ...parsers.tsv import TSVTaxonomyParser
        
        file_path = Path(input_path)
        
        if format_type == "auto" or format_type == "tsv":
            parser = TSVTaxonomyParser()
            # Handle isinstance check safely for tests
            try:
                path_to_check = file_path if isinstance(file_path, Path) else Path(input_path)
            except TypeError:
                # Handle mock objects in tests that can't be used with isinstance
                path_to_check = Path(input_path)
            
            if hasattr(parser, 'can_parse') and parser.can_parse(path_to_check):
                return parser.parse(file_path)
            else:
                raise ValidationError(f"Cannot parse input file as TSV: {input_path}")
        else:
            raise ValidationError(f"Unsupported format: {format_type}")

    def _determine_attachment_strategy(self, repository, input_tree: TaxonomyTree, args) -> Dict:
        """Determine how to attach the imported tree."""
        attachment_info = {
            "strategy": args.strategy,
            "database_attachment_node": None,
            "input_root_node": None,
            "replace_target": None
        }

        # Find attachment point in database
        if args.target:
            # Specific node to replace
            target_node = repository.get_node_by_name(args.target)
            if not target_node:
                raise ValidationError(f"Target node not found in database: {args.target}")
            attachment_info["database_attachment_node"] = target_node
            attachment_info["replace_target"] = target_node
            
        elif args.attach_to:
            # Attach to existing node by name
            attach_node = repository.get_node_by_name(args.attach_to)
            if not attach_node:
                raise ValidationError(f"Attachment node not found in database: {args.attach_to}")
            attachment_info["database_attachment_node"] = attach_node
            
        elif args.attach_to_id:
            # Attach to existing node by ID
            attach_node = repository.get_node(args.attach_to_id)
            if not attach_node:
                raise ValidationError(f"Attachment node not found in database: {args.attach_to_id}")
            attachment_info["database_attachment_node"] = attach_node

        # Find root node in input tree
        if args.root_node:
            # User-specified root
            input_root = None
            for node in input_tree:
                if node.name == args.root_node:
                    input_root = node
                    break
            if not input_root:
                raise ValidationError(f"Root node not found in input file: {args.root_node}")
            attachment_info["input_root_node"] = input_root
            
        elif args.auto_root:
            # Auto-detect root (node with no parent or parent not in tree)
            potential_roots = []
            orphaned_nodes = []  # Nodes with no parent that should be attached
            
            for node in input_tree:
                if node.parent_id is None:
                    # If we have an attachment point, treat nodes with no parent as orphaned children
                    # that should be attached, not as roots
                    if args.attach_to or args.attach_to_id:
                        orphaned_nodes.append(node)
                    else:
                        potential_roots.append(node)
                elif not input_tree.get_node(node.parent_id):
                    potential_roots.append(node)
            
            # If we have orphaned nodes and an attachment point, don't treat them as roots
            if orphaned_nodes and (args.attach_to or args.attach_to_id):
                # When attaching orphaned nodes, there's no single "input root" - they'll all be attached
                attachment_info["input_root_node"] = None
            elif len(potential_roots) == 1:
                attachment_info["input_root_node"] = potential_roots[0]
            elif len(potential_roots) == 0:
                if not orphaned_nodes:
                    raise ValidationError("No root node found in input file")
                # If we only have orphaned nodes, that's fine - they'll be attached
                attachment_info["input_root_node"] = None
            else:
                root_names = [r.name for r in potential_roots]
                raise ValidationError(f"Multiple potential roots found: {root_names}. Use --root-node to specify.")

        return attachment_info

    def _preview_import(self, repository, input_tree: TaxonomyTree, attachment_info: Dict, args) -> int:
        """Preview what changes would be made."""
        print("🔍 Dry run - Changes that would be made:")
        print(f"   📥 Input tree: {input_tree.node_count} nodes")
        print(f"   🎯 Strategy: {attachment_info['strategy']}")
        
        db_node = attachment_info["database_attachment_node"]
        input_root = attachment_info["input_root_node"]
        
        if attachment_info["strategy"] == "replace":
            target = attachment_info["replace_target"]
            print(f"   🔄 Replace: {target.name} (ID: {target.tax_id})")
            print(f"   📝 Keep names: {args.keep_names}")
            print(f"   ➕ Would add/update {input_tree.node_count} nodes")
            
        elif attachment_info["strategy"] == "merge":
            print(f"   🔗 Attach to: {db_node.name} (ID: {db_node.tax_id})")
            if input_root:
                print(f"   📍 Input root: {input_root.name}")
            
            # Count what would be added vs skipped
            conflicts = self._analyze_conflicts(repository, input_tree, args.on_conflict)
            print(f"   ➕ Would add: {conflicts['add_count']} new nodes")
            print(f"   ⚠️  Conflicts: {conflicts['conflict_count']} existing nodes")
            print(f"   🎯 Conflict action: {args.on_conflict}")

        print(f"   💡 Use without --dry-run to apply changes")
        return 0

    def _execute_import(self, repository, input_tree: TaxonomyTree, attachment_info: Dict, args) -> int:
        """Execute the tree import."""
        if attachment_info["strategy"] == "replace":
            return self._execute_replace_strategy(repository, input_tree, attachment_info, args)
        else:
            return self._execute_merge_strategy(repository, input_tree, attachment_info, args)

    def _execute_merge_strategy(self, repository, input_tree: TaxonomyTree, attachment_info: Dict, args) -> int:
        """Execute merge strategy - add new nodes under attachment point."""
        db_attachment = attachment_info["database_attachment_node"]
        input_root = attachment_info["input_root_node"]
        
        added_count = 0
        updated_count = 0
        skipped_count = 0
        
        # Get next available tax_id
        next_tax_id = repository.get_next_tax_id()
        
        # Process nodes in dependency order (parents before children)
        processed_nodes = set()
        node_id_mapping = {}  # Map old_id -> new_id
        
        # If input_root should be merged with attachment point
        if input_root and args.attach_to and input_root.name == args.attach_to:
            # The root node already exists, map its ID
            node_id_mapping[input_root.tax_id] = db_attachment.tax_id
            processed_nodes.add(input_root.tax_id)
            print(f"   🔗 Merging input root '{input_root.name}' with existing node")
        elif input_root:
            # Create the root as a child of attachment point
            new_root = self._create_node_copy(input_root, db_attachment.tax_id, next_tax_id)
            
            existing = repository.get_node_by_name(new_root.name)
            if existing and args.on_conflict == "skip":
                node_id_mapping[input_root.tax_id] = existing.tax_id
                skipped_count += 1
                print(f"   ⚠️  Skipped existing node: {new_root.name}")
            elif existing and args.on_conflict == "update":
                # Update existing node
                repository.update_node(existing.tax_id, new_root.name, new_root.rank, new_root.parent_id)
                node_id_mapping[input_root.tax_id] = existing.tax_id
                updated_count += 1
                print(f"   🔄 Updated node: {new_root.name}")
            else:
                repository.add_node(new_root)
                node_id_mapping[input_root.tax_id] = new_root.tax_id
                added_count += 1
                next_tax_id += 1
                print(f"   ➕ Added node: {new_root.name} (ID: {new_root.tax_id})")
            
            processed_nodes.add(input_root.tax_id)
        else:
            # No input root - handle orphaned nodes directly
            # First, process all nodes with parent_id=None as children of attachment point
            for node in input_tree:
                if node.parent_id is None:
                    new_node = self._create_node_copy(node, db_attachment.tax_id, next_tax_id)
                    
                    existing = repository.get_node_by_name(new_node.name)
                    if existing and args.on_conflict == "skip":
                        node_id_mapping[node.tax_id] = existing.tax_id
                        skipped_count += 1
                        print(f"   ⚠️  Skipped existing node: {new_node.name}")
                    elif existing and args.on_conflict == "update":
                        # Update existing node
                        repository.update_node(existing.tax_id, new_node.name, new_node.rank, new_node.parent_id)
                        node_id_mapping[node.tax_id] = existing.tax_id
                        updated_count += 1
                        print(f"   🔄 Updated node: {new_node.name}")
                    else:
                        repository.add_node(new_node)
                        node_id_mapping[node.tax_id] = new_node.tax_id
                        added_count += 1
                        next_tax_id += 1
                        print(f"   ➕ Added node: {new_node.name} (ID: {new_node.tax_id})")
                    
                    processed_nodes.add(node.tax_id)

        # Process remaining nodes
        remaining_nodes = [n for n in input_tree if n.tax_id not in processed_nodes]
        
        while remaining_nodes:
            progress_made = False
            nodes_to_process = remaining_nodes.copy()
            
            for node in nodes_to_process:
                # Check if parent has been processed
                parent_mapped = (node.parent_id is None or 
                               node.parent_id in node_id_mapping or
                               node.parent_id in processed_nodes)
                
                if parent_mapped:
                    # Determine new parent ID
                    if node.parent_id is None:
                        new_parent_id = db_attachment.tax_id
                    else:
                        new_parent_id = node_id_mapping.get(node.parent_id, node.parent_id)
                    
                    new_node = self._create_node_copy(node, new_parent_id, next_tax_id)
                    
                    existing = repository.get_node_by_name(new_node.name)
                    if existing and args.on_conflict == "skip":
                        node_id_mapping[node.tax_id] = existing.tax_id
                        skipped_count += 1
                        print(f"   ⚠️  Skipped existing node: {new_node.name}")
                    elif existing and args.on_conflict == "update":
                        repository.update_node(existing.tax_id, new_node.name, new_node.rank, new_node.parent_id)
                        node_id_mapping[node.tax_id] = existing.tax_id
                        updated_count += 1
                        print(f"   🔄 Updated node: {new_node.name}")
                    else:
                        repository.add_node(new_node)
                        node_id_mapping[node.tax_id] = new_node.tax_id
                        added_count += 1
                        next_tax_id += 1
                        print(f"   ➕ Added node: {new_node.name} (ID: {new_node.tax_id})")
                    
                    processed_nodes.add(node.tax_id)
                    remaining_nodes.remove(node)
                    progress_made = True
            
            if not progress_made and remaining_nodes:
                unprocessed_names = [n.name for n in remaining_nodes]
                raise ValidationError(f"Cannot resolve parent dependencies for nodes: {unprocessed_names}")

        # Summary
        print(f"✅ Import completed:")
        print(f"   ➕ Nodes added: {added_count}")
        print(f"   🔄 Nodes updated: {updated_count}")
        print(f"   ⚠️  Nodes skipped: {skipped_count}")
        
        return 0

    def _execute_replace_strategy(self, repository, input_tree: TaxonomyTree, attachment_info: Dict, args) -> int:
        """Execute replace strategy - replace existing node with imported tree."""
        target_node = attachment_info["replace_target"]
        input_root = attachment_info["input_root_node"]
        
        print(f"🔄 Replacing node: {target_node.name} (ID: {target_node.tax_id})")
        
        # Get target's parent and children
        target_parent_id = target_node.parent_id
        target_children = repository.get_children(target_node.tax_id)
        
        if not args.force and target_children:
            child_count = len(target_children)
            raise ValidationError(f"Target node has {child_count} children. Use --force to proceed with replacement.")
        
        # Remove target node and its subtree
        removed_count = repository.remove_subtree(target_node.tax_id)
        print(f"   🗑️  Removed {removed_count} nodes")
        
        # Determine the name for the replacement root
        if args.keep_names == "database":
            replacement_name = target_node.name
        elif args.keep_names == "file":
            replacement_name = input_root.name if input_root else target_node.name
        else:  # prompt
            replacement_name = input(f"Enter name for replacement node (database: '{target_node.name}', file: '{input_root.name if input_root else 'N/A'}'): ")
            if not replacement_name:
                replacement_name = target_node.name
        
        # Create replacement root with target's original ID and parent
        replacement_root = TaxonomyNode(
            tax_id=target_node.tax_id,  # Keep original ID
            name=replacement_name,
            rank=input_root.rank if input_root else target_node.rank,
            parent_id=target_parent_id,
            description=input_root.description if input_root else target_node.description
        )
        
        repository.add_node(replacement_root)
        print(f"   ➕ Added replacement root: {replacement_root.name} (ID: {replacement_root.tax_id})")
        
        # Add remaining nodes from input tree
        added_count = 1  # Count the root
        next_tax_id = repository.get_next_tax_id()
        node_id_mapping = {}
        
        if input_root:
            node_id_mapping[input_root.tax_id] = replacement_root.tax_id
        
        # Add child nodes - exclude root and external parent references
        if input_root:
            # Find nodes that should be processed (descendants of the root)
            nodes_to_process = []
            processed_parents = set()
            
            def collect_descendants(node_id):
                for node in input_tree:
                    if node.parent_id == node_id and node.tax_id not in processed_parents:
                        nodes_to_process.append(node)
                        processed_parents.add(node.tax_id)
                        collect_descendants(node.tax_id)
            
            collect_descendants(input_root.tax_id)
            remaining_nodes = nodes_to_process
        else:
            remaining_nodes = list(input_tree)
        
        while remaining_nodes:
            progress_made = False
            nodes_to_process = remaining_nodes.copy()
            
            for node in nodes_to_process:
                # Check if parent is mapped in input tree
                parent_mapped = (node.parent_id in node_id_mapping or
                               (node.parent_id == input_root.tax_id if input_root else False))
                
                # For replace strategy, also check if parent exists in database
                database_parent = None
                if not parent_mapped:
                    # Look for parent by name in the database (common for replace strategy)
                    parent_node_in_tree = input_tree.get_node(node.parent_id)
                    if parent_node_in_tree:
                        database_parent = repository.get_node_by_name(parent_node_in_tree.name)
                        if database_parent:
                            parent_mapped = True
                
                if parent_mapped:
                    if database_parent:
                        new_parent_id = database_parent.tax_id
                    else:
                        new_parent_id = node_id_mapping.get(node.parent_id, replacement_root.tax_id)
                    new_node = self._create_node_copy(node, new_parent_id, next_tax_id)
                    
                    repository.add_node(new_node)
                    node_id_mapping[node.tax_id] = new_node.tax_id
                    added_count += 1
                    next_tax_id += 1
                    print(f"   ➕ Added node: {new_node.name} (ID: {new_node.tax_id})")
                    
                    remaining_nodes.remove(node)
                    progress_made = True
            
            if not progress_made and remaining_nodes:
                unprocessed_names = [n.name for n in remaining_nodes]
                raise ValidationError(f"Cannot resolve parent dependencies for nodes: {unprocessed_names}")
        
        print(f"✅ Replace completed:")
        print(f"   🔄 Replaced: {target_node.name}")
        print(f"   ➕ Added: {added_count} nodes")
        print(f"   📝 Final name: {replacement_root.name}")
        
        return 0

    def _create_node_copy(self, original: TaxonomyNode, new_parent_id: int, new_tax_id: int) -> TaxonomyNode:
        """Create a copy of a node with new IDs."""
        return TaxonomyNode(
            tax_id=new_tax_id,
            name=original.name,
            rank=original.rank,
            parent_id=new_parent_id,
            description=original.description or ""
        )

    def _analyze_conflicts(self, repository, input_tree: TaxonomyTree, conflict_strategy: str) -> Dict:
        """Analyze potential conflicts between input and database nodes."""
        conflicts = {"add_count": 0, "conflict_count": 0, "conflicts": []}
        
        for node in input_tree:
            existing = repository.get_node_by_name(node.name)
            if existing:
                conflicts["conflict_count"] += 1
                conflicts["conflicts"].append({
                    "name": node.name,
                    "input_id": node.tax_id,
                    "db_id": existing.tax_id
                })
            else:
                conflicts["add_count"] += 1
        
        return conflicts