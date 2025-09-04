"""Purge command for removing nodes without genomic data."""

import argparse
import os
from typing import Optional, Dict, Any
from pathlib import Path

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError
from ...database.sqlite import SQLiteTaxonomyRepository


class PurgeCommand(BaseCommand):
    """Command to purge taxonomy nodes without genomic representation."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the purge command parser."""
        parser = subparsers.add_parser(
            "purge",
            help="Remove nodes without genomic data",
            description="""Remove taxonomy nodes that don't have genomic representation.
            
This command implements the purge_database functionality that cleans up
taxonomy by keeping only end nodes containing genomes with FASTA files
and their complete lineages to the root. This results in a slim taxonomy
corresponding to where genomic representation exists.""",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Purge nodes without FASTA files (default behavior)
  flextaxd purge --database my_db.ftd
  
  # Purge but allow nodes with any genome data (not just FASTA files)  
  flextaxd purge --database my_db.ftd --allow-metadata-only
  
  # Dry run to see what would be purged without making changes
  flextaxd purge --database my_db.ftd --dry-run
  
  # Force purge without confirmation prompts
  flextaxd purge --database my_db.ftd --force
            """,
        )

        parser.add_argument(
            "--database",
            "-d",
            type=str,
            required=True,
            help="Database file path (.ftd)",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be purged without making changes",
        )

        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt and proceed with purging",
        )

        parser.add_argument(
            "--allow-metadata-only",
            action="store_true",
            help="Keep nodes with genome metadata even without FASTA files",
        )

        parser.add_argument(
            "--backup",
            type=str,
            help="Create backup database before purging (recommended)",
        )

        parser.add_argument(
            "--stats-only",
            action="store_true",
            help="Only show purge statistics without performing purge",
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the purge command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)
            
            # Additional safety validations
            self._validate_purge_safety(args)

            # Create backup if requested
            if args.backup:
                self._create_backup(args.database, args.backup)

            # Load database
            with SQLiteTaxonomyRepository(args.database) as repository:
                # Get current tree
                tree = repository.load_tree()
                
                # Get initial statistics
                initial_stats = tree.get_tree_statistics()
                self.logger.info(f"Initial database: {initial_stats['node_count']} nodes, {initial_stats['genome_count']} genomes")
                
                # Determine purging criteria
                require_fasta = not args.allow_metadata_only
                
                # Perform dry run or get purge statistics
                if args.dry_run or args.stats_only:
                    purge_stats = self._analyze_purge_impact(tree, require_fasta, args.force)
                    self._display_purge_analysis(purge_stats, args.dry_run)
                    
                    if args.dry_run:
                        print("\nDry run completed. Use --force to perform actual purging.")
                    return 0
                
                # Get user confirmation unless forced
                if not args.force:
                    purge_stats = self._analyze_purge_impact(tree, require_fasta, args.force)
                    
                    if not self._confirm_purge(purge_stats):
                        print("Purge cancelled by user.")
                        return 0
                
                # Perform the actual purge
                print("Performing taxonomy purge...")
                purge_stats = tree.purge_nodes_without_genomes(require_fasta_files=require_fasta, force=args.force)
                
                # Check for warnings
                if "warning" in purge_stats:
                    print(f"Warning: {purge_stats['warning']}")
                    return 0
                
                # Save the purged tree back to database
                if not (args.dry_run or args.stats_only):
                    repository.save_tree(tree)
                
                # Display results
                self._display_purge_results(purge_stats)
                
                print(f"\nPurge completed successfully!")
                if args.backup:
                    print(f"Original database backed up to: {args.backup}")

            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1

        except Exception as e:
            self.logger.exception("Unexpected error during purge")
            print(f"Unexpected error: {e}")
            return 2

    def _create_backup(self, database_path: str, backup_path: str) -> None:
        """Create a backup of the database."""
        import shutil
        
        try:
            shutil.copy2(database_path, backup_path)
            self.logger.info(f"Database backed up to {backup_path}")
            print(f"Database backed up to: {backup_path}")
        except OSError as e:
            raise ValidationError(f"Failed to create backup: {e}")

    def _analyze_purge_impact(self, tree, require_fasta: bool, force: bool) -> Dict[str, Any]:
        """Analyze the impact of purging without making changes."""
        # Create a copy of the tree for analysis
        import copy
        analysis_tree = copy.deepcopy(tree)
        
        # Get purge statistics
        stats = analysis_tree.purge_nodes_without_genomes(require_fasta_files=require_fasta, force=force)
        
        return stats

    def _display_purge_analysis(self, stats: Dict[str, Any], is_dry_run: bool) -> None:
        """Display purge impact analysis."""
        action_word = "would be" if is_dry_run else "will be"
        
        print("\nPurge Analysis:")
        print("=" * 40)
        
        if "warning" in stats:
            print(f"Warning: {stats['warning']}")
            return
            
        print(f"Nodes before purge: {stats['nodes_before']:,}")
        print(f"Nodes after purge:  {stats['nodes_after']:,}")
        print(f"Nodes {action_word} removed: {stats['nodes_removed']:,}")
        
        if stats['nodes_before'] > 0:
            removal_pct = (stats['nodes_removed'] / stats['nodes_before']) * 100
            print(f"Removal percentage: {removal_pct:.1f}%")
        
        print(f"\nGenomes retained: {stats['genomes_retained']:,}")
        print(f"Lineages preserved: {stats['lineages_preserved']:,}")
        print(f"Nodes with genomes: {stats['nodes_with_genomes']:,}")
        print(f"Essential nodes kept: {stats['essential_nodes_kept']:,}")

    def _confirm_purge(self, stats: Dict[str, Any]) -> bool:
        """Ask user for confirmation before purging."""
        if "warning" in stats:
            print(f"Warning: {stats['warning']}")
            return False
            
        print("\nPurge Impact Summary:")
        print(f"  • {stats['nodes_removed']:,} nodes will be removed")
        print(f"  • {stats['nodes_after']:,} nodes will remain")
        print(f"  • {stats['genomes_retained']:,} genomes will be retained")
        
        if stats['nodes_before'] > 0:
            removal_pct = (stats['nodes_removed'] / stats['nodes_before']) * 100
            print(f"  • {removal_pct:.1f}% of nodes will be removed")
        
        print("\nThis operation cannot be undone!")
        response = input("\nProceed with purging? [y/N]: ").lower().strip()
        return response in ['y', 'yes']

    def _display_purge_results(self, stats: Dict[str, Any]) -> None:
        """Display final purge results."""
        print("\nPurge Results:")
        print("=" * 40)
        
        if "warning" in stats:
            print(f"Warning: {stats['warning']}")
            return
            
        print(f"Nodes removed: {stats['nodes_removed']:,}")
        print(f"Nodes remaining: {stats['nodes_after']:,}")
        print(f"Genomes retained: {stats['genomes_retained']:,}")
        
        if stats['nodes_before'] > 0:
            reduction_pct = (stats['nodes_removed'] / stats['nodes_before']) * 100
            print(f"Database size reduction: {reduction_pct:.1f}%")

    def _validate_purge_safety(self, args: argparse.Namespace) -> None:
        """Perform additional safety validations before purging."""
        from pathlib import Path
        
        # Ensure we're not accidentally purging a critical database
        db_path = Path(args.database)
        
        # Check if database file is writable (for non-dry-run operations)
        if not (args.dry_run or args.stats_only):
            if not db_path.exists():
                raise ValidationError(f"Database file does not exist: {args.database}")
            
            if not db_path.is_file():
                raise ValidationError(f"Database path is not a file: {args.database}")
                
            # Check write permissions
            if not os.access(db_path.parent, os.W_OK):
                raise ValidationError(f"No write permission for database directory: {db_path.parent}")
        
        # Recommend backup if not provided and not dry-run
        if not (args.dry_run or args.stats_only or args.backup):
            if not args.force:
                self.logger.warning("No backup specified. Consider using --backup for safety.")
                response = input("Continue without backup? [y/N]: ").lower().strip()
                if response not in ['y', 'yes']:
                    print("Operation cancelled. Use --backup to create a backup first.")
                    raise ValidationError("Operation cancelled by user")
        
        # Validate backup path if provided
        if args.backup:
            backup_path = Path(args.backup)
            if backup_path.exists() and not args.force:
                response = input(f"Backup file {args.backup} already exists. Overwrite? [y/N]: ").lower().strip()
                if response not in ['y', 'yes']:
                    raise ValidationError("Operation cancelled to prevent overwriting existing backup")
            
            # Check backup directory is writable
            if not backup_path.parent.exists():
                try:
                    backup_path.parent.mkdir(parents=True)
                except OSError as e:
                    raise ValidationError(f"Cannot create backup directory: {e}")
            
            if not os.access(backup_path.parent, os.W_OK):
                raise ValidationError(f"No write permission for backup directory: {backup_path.parent}")