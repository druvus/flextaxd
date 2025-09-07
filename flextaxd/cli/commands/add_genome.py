"""Add-genome command for adding genome information to taxonomy nodes."""

import argparse
from pathlib import Path
from typing import Optional

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError
from ...core.models import GenomeInfo
from ...database.sqlite import SQLiteTaxonomyRepository


class AddGenomeCommand(BaseCommand):
    """Command to add genome information to taxonomy nodes."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the add-genome command parser."""
        parser = subparsers.add_parser(
            "add-genome",
            help="Add genome to taxonomy node",
            description="Add genome information to an existing taxonomy node",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Add genome to existing taxonomy node by ID
  flextaxd add-genome --database my_db.ftd --genome-id "GCF_000005825.2" --tax-id 562 --file-path /data/ecoli.fna
  
  # Add genome to taxonomy node by name
  flextaxd add-genome --database my_db.ftd --genome-id "ecoli_k12" --tax-name "Escherichia coli" --file-path /data/ecoli.fna
  
  # Add genome with comprehensive metadata
  flextaxd add-genome --database my_db.ftd --genome-id "GCF_000005825.2" --tax-id 562 \\
    --file-path /data/ecoli.fna --assembly-accession "GCF_000005825.2" \\
    --sequence-type genome --source "NCBI" --strain "K-12 substr. MG1655"
  
  # Preview addition without making changes
  flextaxd add-genome --database my_db.ftd --genome-id "test_genome" --tax-id 562 --file-path /data/test.fna --dry-run
            """,
        )

        parser.add_argument(
            "--database", "-d", type=str, required=True,
            help="Database file path (.ftd)"
        )

        parser.add_argument(
            "--genome-id", type=str, required=True,
            help="Unique identifier for the genome"
        )

        # Target taxonomy node (mutually exclusive)
        target_group = parser.add_mutually_exclusive_group(required=True)
        target_group.add_argument(
            "--tax-id", type=int,
            help="Taxonomy ID to associate genome with"
        )
        target_group.add_argument(
            "--tax-name", type=str,
            help="Taxonomy node name to associate genome with"
        )

        parser.add_argument(
            "--file-path", type=str,
            help="Path to genome FASTA file"
        )

        parser.add_argument(
            "--assembly-accession", type=str,
            help="Assembly accession (e.g., GCF_000005825.2)"
        )

        parser.add_argument(
            "--nucleotide-accession", type=str,
            help="Nucleotide accession (e.g., NC_000913.3)"
        )

        parser.add_argument(
            "--protein-accession", type=str,
            help="Representative protein accession"
        )


        parser.add_argument(
            "--biosample-accession", type=str,
            help="BioSample accession (e.g., SAMN02604091)"
        )

        parser.add_argument(
            "--sequence-type", type=str, default="genome",
            choices=["genome", "plasmid", "16S", "protein", "other"],
            help="Type of sequence (default: genome)"
        )

        parser.add_argument(
            "--source", type=str, default="custom",
            help="Source of genome data (e.g., NCBI, GTDB, custom)"
        )

        parser.add_argument(
            "--strain", type=str,
            help="Strain information"
        )

        parser.add_argument(
            "--description", type=str,
            help="Description of the genome"
        )

        parser.add_argument(
            "--validate-file", action="store_true", default=True,
            help="Validate that the genome file exists and is accessible (default: True)"
        )

        parser.add_argument(
            "--skip-file-validation", action="store_true",
            help="Skip genome file validation"
        )

        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be added without making changes"
        )

        parser.add_argument(
            "--force", action="store_true",
            help="Force addition even if genome ID already exists"
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the add-genome command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)

            with SQLiteTaxonomyRepository(args.database) as repository:
                # Find target taxonomy node
                target_node = self._find_target_node(repository, args)
                if not target_node:
                    target_identifier = args.tax_id or args.tax_name
                    raise ValidationError(f"Target taxonomy node not found: {target_identifier}")

                # Check if genome ID already exists
                existing_genome = repository.get_genome(args.genome_id)
                if existing_genome and not args.force:
                    raise ValidationError(f"Genome ID '{args.genome_id}' already exists. Use --force to override.")

                # Validate file if provided
                file_validation = self._validate_genome_file(args)

                # Create genome info object
                genome_info = self._create_genome_info(args, target_node.tax_id, file_validation)

                # Validate genome data
                self._validate_genome_info(genome_info)

                if args.dry_run:
                    self._preview_addition(genome_info, target_node, file_validation)
                    return 0
                else:
                    # Add the genome
                    if existing_genome and args.force:
                        repository.update_genome(genome_info)
                        action = "Updated"
                    else:
                        repository.add_genome(genome_info)
                        action = "Added"

                    self.logger.info(f"{action} genome: {genome_info.genome_id} for tax_id {target_node.tax_id}")
                    
                    print(f"✅ Successfully {action.lower()} genome:")
                    print(f"   Genome ID: {genome_info.genome_id}")
                    print(f"   Taxonomy: {target_node.name} (ID: {target_node.tax_id})")
                    if genome_info.assembly_accession:
                        print(f"   Assembly: {genome_info.assembly_accession}")
                    if genome_info.file_path:
                        print(f"   File: {genome_info.file_path}")
                    if genome_info.strain:
                        print(f"   Strain: {genome_info.strain}")
                    
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

    def _find_target_node(self, repository, args):
        """Find target taxonomy node by ID or name."""
        if args.tax_id:
            return repository.get_node(args.tax_id)
        elif args.tax_name:
            return repository.get_node_by_name(args.tax_name)
        return None

    def _validate_genome_file(self, args) -> dict:
        """Validate genome file if path is provided."""
        validation_result = {
            "file_provided": bool(args.file_path),
            "file_exists": False,
            "file_accessible": False,
            "file_size": None,
            "validation_skipped": args.skip_file_validation
        }

        if not args.file_path or args.skip_file_validation:
            return validation_result

        file_path = Path(args.file_path)
        
        # Check existence
        if file_path.exists():
            validation_result["file_exists"] = True
            
            # Check accessibility
            try:
                if file_path.is_file():
                    validation_result["file_accessible"] = True
                    validation_result["file_size"] = file_path.stat().st_size
                else:
                    raise ValidationError(f"Genome file path is not a file: {args.file_path}")
            except PermissionError:
                raise ValidationError(f"Cannot access genome file: {args.file_path}")
        else:
            if args.validate_file:
                raise ValidationError(f"Genome file not found: {args.file_path}")
            else:
                self.logger.warning(f"Genome file not found (will be stored anyway): {args.file_path}")

        return validation_result

    def _create_genome_info(self, args, tax_id: int, file_validation: dict) -> GenomeInfo:
        """Create GenomeInfo object from arguments."""
        return GenomeInfo(
            genome_id=args.genome_id,
            tax_id=tax_id,
            file_path=args.file_path,
            sequence_type=args.sequence_type,
            assembly_accession=args.assembly_accession,
            nucleotide_accession=args.nucleotide_accession,
            protein_accession=args.protein_accession,
            biosample_accession=args.biosample_accession,
            description=args.description or "",
            source=args.source,
            strain=args.strain,
            sequence_length=None  # Could be calculated from file if needed
        )

    def _validate_genome_info(self, genome_info: GenomeInfo) -> None:
        """Validate genome information."""
        # Use GenomeInfo's built-in validation
        validation_issues = genome_info.validate()
        if validation_issues:
            raise ValidationError(f"Genome validation failed: {'; '.join(validation_issues)}")

        # Validate accessions if provided
        accession_issues = genome_info.validate_accessions()
        if accession_issues:
            self.logger.warning(f"Accession validation warnings: {'; '.join(accession_issues)}")

    def _preview_addition(self, genome_info: GenomeInfo, target_node, file_validation: dict) -> None:
        """Preview what would be added."""
        print("🔍 Dry run - Genome that would be added:")
        print(f"   📊 Genome ID: {genome_info.genome_id}")
        print(f"   🎯 Target taxonomy: {target_node.name} (ID: {target_node.tax_id})")
        print(f"   🧬 Sequence type: {genome_info.sequence_type}")
        print(f"   📝 Source: {genome_info.source}")
        
        if genome_info.assembly_accession:
            print(f"   🔗 Assembly accession: {genome_info.assembly_accession}")
        
        if genome_info.file_path:
            print(f"   📁 File path: {genome_info.file_path}")
            if file_validation["file_exists"]:
                size_mb = file_validation["file_size"] / (1024 * 1024) if file_validation["file_size"] else 0
                print(f"   ✅ File status: Exists ({size_mb:.1f} MB)")
            else:
                print(f"   ❌ File status: Not found")
        
        if genome_info.strain:
            print(f"   🦠 Strain: {genome_info.strain}")
        
        if genome_info.description:
            print(f"   📄 Description: {genome_info.description}")
        
        print(f"   💡 Use without --dry-run to add genome")