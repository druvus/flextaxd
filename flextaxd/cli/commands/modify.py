"""Modify command for editing taxonomy databases."""

import argparse

from ...core.exceptions import DatabaseError, ValidationError
from ...core.models import TaxonomicRank, TaxonomyNode
from ...database.repository import TaxonomyRepository
from ...database.sqlite import SQLiteTaxonomyRepository
from .base import BaseCommand


class ModifyCommand(BaseCommand):
    """Command to modify existing taxonomy databases."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the modify command parser."""
        parser = subparsers.add_parser(
            "modify",
            help="Modify an existing taxonomy database",
            description="Add, remove, or update nodes in a taxonomy database",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  flextaxd modify --database my_db.ftd --add-node "New Species" --parent-id 12345
  flextaxd modify --database my_db.ftd --remove-node 67890
  flextaxd modify --database my_db.ftd --update-node 12345 --new-name "Updated Name"
            """,
        )

        parser.add_argument(
            "--database",
            "-d",
            type=str,
            required=True,
            help="Database file path (.ftd)",
        )

        # Modification operations (mutually exclusive)
        operation_group = parser.add_mutually_exclusive_group(required=True)

        operation_group.add_argument(
            "--add-node", type=str, help="Add a new node with the given name"
        )

        operation_group.add_argument(
            "--remove-node", type=int, help="Remove node with the given taxonomic ID"
        )

        operation_group.add_argument(
            "--mod-file", type=str, help="Import taxonomy from another file"
        )

        operation_group.add_argument(
            "--merge-database", type=str, help="Merge another database into this one"
        )

        operation_group.add_argument(
            "--update-node", type=int, help="Update node with the given taxonomic ID"
        )

        # Node properties
        parser.add_argument(
            "--parent-id", type=int, help="Parent taxonomic ID for new or updated node"
        )

        parser.add_argument(
            "--rank",
            type=str,
            choices=[rank.value for rank in TaxonomicRank],
            help="Taxonomic rank for new or updated node",
        )

        parser.add_argument("--new-name", type=str, help="New name for updated node")

        parser.add_argument(
            "--new-id",
            type=int,
            help="New taxonomic ID for the node (use with caution)",
        )

        # Database merging parameters
        parser.add_argument(
            "--parent", type=str, help="Parent node name for merging operations"
        )

        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace existing branch when merging",
        )

        parser.add_argument(
            "--format",
            type=str,
            choices=["auto", "tsv", "ncbi", "qiime", "gtdb", "silva", "cansnper"],
            default="auto",
            help="Format of the input file for --mod-file (default: auto-detect)",
        )

        # Options
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force operation even if it might break tree structure",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

        return parser

    def execute(self, args: argparse.Namespace) -> int | None:
        """Execute the modify command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)

            with SQLiteTaxonomyRepository(args.database) as repository:
                if args.add_node:
                    return self._add_node(repository, args)
                elif args.remove_node:
                    return self._remove_node(repository, args)
                elif args.update_node:
                    return self._update_node(repository, args)
                elif args.mod_file:
                    return self._import_from_file(repository, args)
                elif args.merge_database:
                    return self._merge_database(repository, args)

            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1

    def _add_node(
        self, repository: TaxonomyRepository, args: argparse.Namespace
    ) -> int:
        """Add a new node to the database."""
        if not args.parent_id:
            raise ValidationError("--parent-id is required when adding a node")

        # Check if parent exists
        parent_node = repository.get_node(args.parent_id)
        if not parent_node:
            raise ValidationError(f"Parent node {args.parent_id} does not exist")

        # Determine taxonomic ID for new node
        # In a real implementation, you'd want a more sophisticated ID assignment
        stats = repository.get_statistics()
        new_tax_id = args.new_id if args.new_id else stats["node_count"] + 1000

        # Check if ID already exists
        if repository.get_node(new_tax_id):
            raise ValidationError(f"Node with ID {new_tax_id} already exists")

        # Determine rank
        rank = TaxonomicRank.CUSTOM
        if args.rank:
            rank = TaxonomicRank(args.rank)

        # Validate that node is not becoming its own parent
        if args.parent_id == new_tax_id:
            raise ValidationError(
                f"Cannot add node '{args.add_node}' (ID: {new_tax_id}) - would create circular reference (node as its own parent)"
            )

        # Create new node
        new_node = TaxonomyNode(
            tax_id=new_tax_id, name=args.add_node, rank=rank, parent_id=args.parent_id
        )

        if args.dry_run:
            print(f"Would add node: {new_node.name} (ID: {new_node.tax_id})")
            print(f"  Parent: {parent_node.name} (ID: {parent_node.tax_id})")
            print(f"  Rank: {new_node.rank.value}")
            return 0

        repository.add_node(new_node)
        print(f"Added node: {new_node.name} (ID: {new_node.tax_id})")
        return 0

    def _remove_node(
        self, repository: TaxonomyRepository, args: argparse.Namespace
    ) -> int:
        """Remove a node from the database."""
        node = repository.get_node(args.remove_node)
        if not node:
            raise ValidationError(f"Node {args.remove_node} does not exist")

        # Check for children
        children = repository.get_children(args.remove_node)
        if children and not args.force:
            raise ValidationError(
                f"Node {args.remove_node} has {len(children)} children. "
                "Use --force to remove anyway (children will be orphaned)"
            )

        if args.dry_run:
            print(f"Would remove node: {node.name} (ID: {node.tax_id})")
            if children:
                print(f"  Warning: {len(children)} children would be orphaned")
            return 0

        repository.delete_node(args.remove_node)
        print(f"Removed node: {node.name} (ID: {node.tax_id})")
        if children:
            print(f"  Warning: {len(children)} children were orphaned")
        return 0

    def _update_node(
        self, repository: TaxonomyRepository, args: argparse.Namespace
    ) -> int:
        """Update an existing node in the database."""
        node = repository.get_node(args.update_node)
        if not node:
            raise ValidationError(f"Node {args.update_node} does not exist")

        # Determine new values
        new_name = args.new_name if args.new_name else node.name
        new_parent_id = args.parent_id if args.parent_id is not None else node.parent_id
        new_rank = TaxonomicRank(args.rank) if args.rank else node.rank

        # Validate new parent exists if changing
        if new_parent_id != node.parent_id and new_parent_id is not None:
            parent_node = repository.get_node(new_parent_id)
            if not parent_node:
                raise ValidationError(f"New parent node {new_parent_id} does not exist")

        # Validate that node is not becoming its own parent
        if new_parent_id == node.tax_id:
            raise ValidationError(
                f"Cannot update node '{node.name}' (ID: {node.tax_id}) - would create circular reference (node as its own parent)"
            )

        # Create updated node
        updated_node = TaxonomyNode(
            tax_id=node.tax_id, name=new_name, rank=new_rank, parent_id=new_parent_id
        )

        if args.dry_run:
            print(f"Would update node {node.tax_id}:")
            print(f"  Name: {node.name} -> {updated_node.name}")
            print(f"  Rank: {node.rank.value} -> {updated_node.rank.value}")
            print(f"  Parent: {node.parent_id} -> {updated_node.parent_id}")
            return 0

        repository.update_node(updated_node)
        print(f"Updated node: {updated_node.name} (ID: {updated_node.tax_id})")
        return 0

    def _import_from_file(
        self, repository: TaxonomyRepository, args: argparse.Namespace
    ) -> int:
        """Import taxonomy from another file."""
        from pathlib import Path

        from ...parsers import (
            CanSNPerTaxonomyParser,
            NCBITaxonomyParser,
            QIIMETaxonomyParser,
            SILVATaxonomyParser,
            TSVTaxonomyParser,
        )
        from ...parsers.registry import registry

        # Validate input file
        mod_file = Path(args.mod_file)
        if not mod_file.exists():
            raise ValidationError(f"Modification file not found: {args.mod_file}")

        # Register parsers
        parser_classes = [
            TSVTaxonomyParser,
            NCBITaxonomyParser,
            QIIMETaxonomyParser,
            SILVATaxonomyParser,
            CanSNPerTaxonomyParser,
        ]
        for parser_class in parser_classes:
            try:
                registry.register(parser_class)  # type: ignore[type-abstract]
            except Exception:
                pass  # Already registered

        # Find appropriate parser
        if args.format == "auto":
            parser = registry.find_parser(mod_file)
            if parser is None:
                raise ValidationError(f"Cannot auto-detect format for: {args.mod_file}")
            self.logger.info(f"Auto-detected format: {parser.parser_name}")
        else:
            # Use format directly - no more aliases needed with proper GTDB parser
            actual_format = args.format

            try:
                parser = registry.get_parser(actual_format)
            except:
                raise ValidationError(f"Unknown format: {args.format}")

            # Validate that the input file actually matches the specified format
            if not parser.can_parse(mod_file):
                self.logger.warning(
                    f"Modification file does not appear to match specified format '{args.format}'. "
                    f"The parser for '{args.format}' cannot validate this file."
                )

                # Try auto-detection to suggest the correct format
                suggested_parser = registry.find_parser(mod_file)
                if (
                    suggested_parser
                    and suggested_parser.parser_name != parser.parser_name
                ):
                    raise ValidationError(
                        f"Modification file does not match specified format '{args.format}'. "
                        f"Auto-detection suggests format '{suggested_parser.parser_name}'. "
                        f"Use --format {suggested_parser.parser_name} or --format auto"
                    )
                else:
                    raise ValidationError(
                        f"Modification file does not match specified format '{args.format}'. "
                        f"Please verify the file format or use --format auto for automatic detection."
                    )

        # Parse the modification file
        self.logger.info(f"Parsing modification file: {args.mod_file}")
        mod_tree = parser.parse(mod_file)

        # Get current tree from database
        current_tree = repository.load_tree()

        # Find parent node for insertion if specified
        parent_node = None
        if args.parent:
            # Find parent by name
            for node in current_tree:
                if node.name.lower() == args.parent.lower():
                    parent_node = node
                    break

            if parent_node is None:
                raise ValidationError(
                    f"Parent node '{args.parent}' not found in database"
                )

        # Create name-to-ID mapping for existing database nodes
        existing_name_to_id = {}
        max_existing_id = 0
        for node in current_tree:
            existing_name_to_id[node.name.lower()] = node.tax_id
            max_existing_id = max(max_existing_id, node.tax_id)

        # Generate new IDs starting from a safe number to avoid conflicts
        next_available_id = max_existing_id + 1000

        # Import nodes from modification tree with proper parent resolution
        nodes_added = 0
        nodes_updated = 0

        if args.dry_run:
            print(f"Would import {mod_tree.node_count} nodes from {args.mod_file}")
            if parent_node:
                print(
                    f"Would attach to parent: {parent_node.name} (ID: {parent_node.tax_id})"
                )
            return 0

        for mod_node in mod_tree:
            # Resolve parent ID by looking up parent name in existing database or using parent attachment
            adjusted_parent_id = None

            if mod_node.parent_id is not None:
                # Find the parent node in the modification tree
                mod_parent = mod_tree.get_node(mod_node.parent_id)
                if mod_parent:
                    # Check if this parent is a root node that should be attached to --parent
                    if parent_node and mod_parent.parent_id is None:
                        # This parent is a root in modification tree, attach it to specified parent
                        adjusted_parent_id = existing_name_to_id.get(
                            mod_parent.name.lower(), parent_node.tax_id
                        )
                    else:
                        # Look up this parent name in the existing database or newly added nodes
                        existing_parent_id = existing_name_to_id.get(
                            mod_parent.name.lower()
                        )
                        if existing_parent_id:
                            adjusted_parent_id = existing_parent_id
                        else:
                            # Parent doesn't exist in database yet - might be added by this import
                            # We'll handle this in a second pass
                            self.logger.warning(
                                f"Parent '{mod_parent.name}' not found in existing database for node '{mod_node.name}'"
                            )
                            continue
            elif parent_node:
                # Root node in modification tree - attach to specified parent
                adjusted_parent_id = parent_node.tax_id

            # Check if node with same name already exists (by name, not tax_id)
            existing_node_id = existing_name_to_id.get(mod_node.name.lower())
            existing_node = (
                current_tree.get_node(existing_node_id) if existing_node_id else None
            )

            if existing_node:
                if args.replace:
                    # Validate that node is not becoming its own parent
                    if adjusted_parent_id == existing_node.tax_id:
                        self.logger.error(
                            f"Cannot replace node '{mod_node.name}' (ID: {existing_node.tax_id}) - would create circular reference (node as its own parent)"
                        )
                        continue

                    # Update existing node
                    updated_node = TaxonomyNode(
                        tax_id=existing_node.tax_id,  # Keep original database ID
                        name=mod_node.name,
                        rank=mod_node.rank,
                        parent_id=adjusted_parent_id,
                    )
                    repository.update_node(updated_node)
                    current_tree._nodes[existing_node.tax_id] = updated_node
                    nodes_updated += 1
                else:
                    self.logger.warning(
                        f"Node '{mod_node.name}' already exists, skipping"
                    )
            else:
                # Add new node with a safe, non-conflicting ID
                new_tax_id = next_available_id
                next_available_id += 1

                # Validate that new node is not becoming its own parent
                if adjusted_parent_id == new_tax_id:
                    self.logger.error(
                        f"Cannot add node '{mod_node.name}' (ID: {new_tax_id}) - would create circular reference (node as its own parent)"
                    )
                    continue

                new_node = TaxonomyNode(
                    tax_id=new_tax_id,
                    name=mod_node.name,
                    rank=mod_node.rank,
                    parent_id=adjusted_parent_id,
                )
                repository.add_node(new_node)
                current_tree.add_node(new_node)
                existing_name_to_id[mod_node.name.lower()] = (
                    new_tax_id  # Update mapping
                )
                nodes_added += 1

        print("Import completed:")
        print(f"  Nodes added: {nodes_added}")
        print(f"  Nodes updated: {nodes_updated}")

        return 0

    def _merge_database(
        self, repository: TaxonomyRepository, args: argparse.Namespace
    ) -> int:
        """Merge another database into this one."""
        from pathlib import Path

        # Validate source database
        source_db_path = Path(args.merge_database)
        if not source_db_path.exists():
            raise ValidationError(f"Source database not found: {args.merge_database}")

        # Load source database
        with SQLiteTaxonomyRepository(source_db_path) as source_repo:
            source_tree = source_repo.load_tree()

        # Get current tree
        current_tree = repository.load_tree()

        # Find parent node for attachment if specified
        parent_node = None
        if args.parent:
            for node in current_tree:
                if node.name.lower() == args.parent.lower():
                    parent_node = node
                    break

            if parent_node is None:
                raise ValidationError(
                    f"Parent node '{args.parent}' not found in database"
                )

        # Handle replacement if requested
        if args.replace and parent_node:
            if args.dry_run:
                descendants = repository.get_descendants(parent_node.tax_id)
                print(
                    f"Would replace {len(descendants)} descendants of {parent_node.name}"
                )
                print(
                    f"Would merge {source_tree.node_count} nodes from source database"
                )
                return 0

            # Remove all descendants of parent (recursive deletion)
            descendants = repository.get_descendants(parent_node.tax_id)
            # Sort by depth (deepest first) to avoid foreign key constraint issues
            descendants_by_depth = []
            for desc in descendants:
                path_to_root = repository.get_path_to_root(desc.tax_id)
                depth = len(path_to_root)
                descendants_by_depth.append((depth, desc))

            # Delete deepest nodes first to maintain referential integrity
            descendants_by_depth.sort(key=lambda x: x[0], reverse=True)
            for _, desc in descendants_by_depth:
                repository.delete_node(desc.tax_id)
                if current_tree.get_node(desc.tax_id):
                    current_tree.remove_node(desc.tax_id)

        # Merge nodes from source database
        nodes_added = 0
        nodes_skipped = 0

        if args.dry_run:
            print(
                f"Would merge {source_tree.node_count} nodes from {args.merge_database}"
            )
            if parent_node:
                print(
                    f"Would attach to parent: {parent_node.name} (ID: {parent_node.tax_id})"
                )
            return 0

        # Create ID mapping to avoid conflicts
        id_mapping = {}
        next_available_id = max([node.tax_id for node in current_tree]) + 1
        used_ids = set(node.tax_id for node in current_tree)  # Track all used IDs

        # Get current root for merging
        current_root = None
        for node in current_tree:
            if node.parent_id is None:
                current_root = node
                break

        for source_node in source_tree:
            # Always merge root nodes - map source root to current root
            if source_node.parent_id is None:
                if parent_node:
                    id_mapping[source_node.tax_id] = parent_node.tax_id
                elif current_root:
                    id_mapping[source_node.tax_id] = current_root.tax_id
                else:
                    # No existing root, use source root ID if no conflict
                    id_mapping[source_node.tax_id] = source_node.tax_id
                continue

            # Check for ID conflicts against both existing nodes AND previously assigned IDs
            if source_node.tax_id in used_ids:
                # Assign new ID
                while next_available_id in used_ids:
                    next_available_id += 1
                new_id = next_available_id
                next_available_id += 1
                id_mapping[source_node.tax_id] = new_id
                used_ids.add(new_id)
            else:
                id_mapping[source_node.tax_id] = source_node.tax_id
                used_ids.add(source_node.tax_id)

        # Add nodes with mapped IDs
        for source_node in source_tree:
            # Always skip root nodes since they are merged, not duplicated
            if source_node.parent_id is None:
                continue

            new_id = id_mapping[source_node.tax_id]
            new_parent_id = None

            if source_node.parent_id is not None:
                new_parent_id = id_mapping.get(
                    source_node.parent_id, source_node.parent_id
                )

            if new_id == new_parent_id:
                self.logger.error(
                    f"CIRCULAR REFERENCE: {source_node.name} would be its own parent (id={new_id})"
                )
                continue

            new_node = TaxonomyNode(
                tax_id=new_id,
                name=source_node.name,
                rank=source_node.rank,
                parent_id=new_parent_id,
            )

            try:
                repository.add_node(new_node)
                current_tree.add_node(new_node)
                nodes_added += 1
            except Exception as e:
                self.logger.warning(f"Could not add node {source_node.name}: {e}")
                nodes_skipped += 1

        print("Database merge completed:")
        print(f"  Nodes added: {nodes_added}")
        print(f"  Nodes skipped: {nodes_skipped}")

        return 0
