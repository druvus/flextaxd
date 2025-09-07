"""Add-node command for adding single taxonomy nodes."""

import argparse
from typing import Optional

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError
from ...core.models import TaxonomyNode, TaxonomicRank
from ...database.sqlite import SQLiteTaxonomyRepository


class AddNodeCommand(BaseCommand):
    """Command to add a single taxonomy node to the database."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the add-node command parser."""
        parser = subparsers.add_parser(
            "add-node",
            help="Add a single taxonomy node",
            description="Add a new taxonomy node to an existing database",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Add a species under an existing genus
  flextaxd add-node --database my_db.ftd --name "Escherichia albertii" --parent-id 561 --rank species
  
  # Add a strain under an existing species  
  flextaxd add-node --database my_db.ftd --name "E. coli K-12" --parent-name "Escherichia coli" --rank strain
  
  # Add a custom node with specific taxonomy ID
  flextaxd add-node --database my_db.ftd --name "Custom Group" --parent-id 562 --tax-id 99999 --rank custom
  
  # Preview changes without making them
  flextaxd add-node --database my_db.ftd --name "Test Species" --parent-id 561 --rank species --dry-run
            """,
        )

        parser.add_argument(
            "--database", "-d", type=str, required=True,
            help="Database file path (.ftd)"
        )

        parser.add_argument(
            "--name", type=str, required=True,
            help="Name of the new taxonomy node"
        )

        # Parent specification (mutually exclusive)
        parent_group = parser.add_mutually_exclusive_group(required=True)
        parent_group.add_argument(
            "--parent-id", type=int,
            help="Parent taxonomy ID"
        )
        parent_group.add_argument(
            "--parent-name", type=str,
            help="Parent node name"
        )

        parser.add_argument(
            "--rank", type=str,
            choices=[rank.value for rank in TaxonomicRank],
            default="custom",
            help="Taxonomic rank (default: custom)"
        )

        parser.add_argument(
            "--tax-id", type=int,
            help="Specific taxonomy ID for the new node (auto-generated if not specified)"
        )


        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be added without making changes"
        )

        parser.add_argument(
            "--force", action="store_true",
            help="Force addition even if node name already exists"
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the add-node command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)

            with SQLiteTaxonomyRepository(args.database) as repository:
                # Find parent node
                parent_node = self._find_parent_node(repository, args)
                if not parent_node:
                    parent_identifier = args.parent_id or args.parent_name
                    raise ValidationError(f"Parent node not found: {parent_identifier}")

                # Determine taxonomy ID
                if args.tax_id:
                    # Check if custom tax_id already exists
                    if repository.get_node(args.tax_id):
                        if not args.force:
                            raise ValidationError(f"Node with tax_id {args.tax_id} already exists. Use --force to override.")
                        self.logger.warning(f"Overriding existing node with tax_id {args.tax_id}")
                    tax_id = args.tax_id
                else:
                    # Auto-generate next available ID
                    tax_id = repository.get_next_tax_id()

                # Check for duplicate names
                existing_node = repository.get_node_by_name(args.name)
                if existing_node and not args.force:
                    raise ValidationError(f"Node with name '{args.name}' already exists (ID: {existing_node.tax_id}). Use --force to add anyway.")

                # Create the new node
                try:
                    rank = TaxonomicRank(args.rank)
                except ValueError:
                    raise ValidationError(f"Invalid rank: {args.rank}")

                new_node = TaxonomyNode(
                    tax_id=tax_id,
                    name=args.name,
                    rank=rank,
                    parent_id=parent_node.tax_id
                )

                # Validate node structure
                self._validate_node_addition(repository, new_node, parent_node)

                if args.dry_run:
                    self._preview_addition(new_node, parent_node)
                    return 0
                else:
                    # Add the node
                    repository.add_node(new_node)
                    self.logger.info(f"Added node: {new_node.name} (ID: {new_node.tax_id})")
                    
                    print(f"✅ Successfully added node:")
                    print(f"   Name: {new_node.name}")
                    print(f"   Tax ID: {new_node.tax_id}")
                    print(f"   Rank: {new_node.rank.value}")
                    print(f"   Parent: {parent_node.name} (ID: {parent_node.tax_id})")
                    
                    return 0

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

    def _find_parent_node(self, repository, args) -> Optional[TaxonomyNode]:
        """Find parent node by ID or name."""
        if args.parent_id:
            return repository.get_node(args.parent_id)
        elif args.parent_name:
            return repository.get_node_by_name(args.parent_name)
        return None

    def _validate_node_addition(self, repository, new_node: TaxonomyNode, parent_node: TaxonomyNode) -> None:
        """Validate that the node addition is valid."""
        # Check for circular references
        if new_node.tax_id == parent_node.tax_id:
            raise ValidationError("Node cannot be its own parent")

        # Check if parent would create cycle
        ancestors = repository.get_ancestors(parent_node.tax_id)
        if new_node.tax_id in [ancestor.tax_id for ancestor in ancestors]:
            raise ValidationError("Adding this node would create a circular reference")

        # Validate rank hierarchy (optional warning)
        if parent_node.rank and new_node.rank:
            parent_rank_value = getattr(parent_node.rank, 'hierarchy_level', 0)
            new_rank_value = getattr(new_node.rank, 'hierarchy_level', 0)
            
            if hasattr(TaxonomicRank, 'hierarchy_level'):
                if parent_rank_value >= new_rank_value and parent_node.rank != TaxonomicRank.CUSTOM and new_node.rank != TaxonomicRank.CUSTOM:
                    self.logger.warning(f"Rank hierarchy warning: {new_node.rank.value} under {parent_node.rank.value} may not follow standard taxonomy")

    def _preview_addition(self, new_node: TaxonomyNode, parent_node: TaxonomyNode) -> None:
        """Preview what would be added."""
        print("🔍 Dry run - Changes that would be made:")
        print(f"   ➕ Add new node:")
        print(f"      Name: {new_node.name}")
        print(f"      Tax ID: {new_node.tax_id}")
        print(f"      Rank: {new_node.rank.value}")
        print(f"      Parent: {parent_node.name} (ID: {parent_node.tax_id})")
        print(f"   💡 Use without --dry-run to apply changes")