"""Export command for exporting taxonomy databases."""

import argparse
from typing import Optional, Dict
from pathlib import Path

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError, ExportError
from ...core.models import TaxonomyTree
from ...database.sqlite import SQLiteTaxonomyRepository
from ...exporters.base import TaxonomyExporter


class ExportCommand(BaseCommand):
    """Command to export taxonomy databases to various formats."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the export command parser."""
        parser = subparsers.add_parser(
            "export",
            help="Export taxonomy database to various formats",
            description="Export a taxonomy database to classifier tools (--classifier creates directory with multiple files) or single file formats (--format creates one file)",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Classifier database formats (create multiple files in directory)
  flextaxd export --database my_db.ftd --classifier ncbi --output ./ncbi_dump/
  flextaxd export --database my_db.ftd --classifier kraken2 --output ./kraken2_db/
  flextaxd export --database my_db.ftd --classifier ganon --output ./ganon_db/
  flextaxd export --database my_db.ftd --classifier centrifuge --output ./centrifuge_db/
  
  # Modern classifier formats
  flextaxd export --database my_db.ftd --classifier metabuli --output ./metabuli_db/
  flextaxd export --database my_db.ftd --classifier metabuli --include-merged --output ./metabuli_db/
  flextaxd export --database my_db.ftd --classifier metacache --output ./metacache_db/
  flextaxd export --database my_db.ftd --classifier metacache --format-type assembly_summary --output ./metacache_db/
  flextaxd export --database my_db.ftd --classifier mmseqs2 --output ./mmseqs2_db/
  flextaxd export --database my_db.ftd --classifier mmseqs2 --sequence-type protein --output ./mmseqs2_db/
  
  # Single file formats
  flextaxd export --database my_db.ftd --format tsv --output taxonomy.tsv
  flextaxd export --database my_db.ftd --format newick --output tree.nwk  
  flextaxd export --database my_db.ftd --format json --output taxonomy.json
  
  # CreateTaxDB compatible single file formats (for nf-core/createtaxdb pipeline)
  flextaxd export --database my_db.ftd --format accession2taxid --output accession2taxid.txt
  flextaxd export --database my_db.ftd --format nucl2taxid --output nucl2taxid.txt
  flextaxd export --database my_db.ftd --format prot2taxid --output prot2taxid.txt
  flextaxd export --database my_db.ftd --format genome_sizes --output genome_sizes.txt
  flextaxd export --database my_db.ftd --format malt_mapdb --output taxonomy.db
            """,
        )

        parser.add_argument(
            "--database",
            "-d",
            type=str,
            required=True,
            help="Database file path (.ftd)",
        )

        # Create mutually exclusive group for classifier vs format
        export_group = parser.add_mutually_exclusive_group(required=True)

        export_group.add_argument(
            "--classifier",
            "-c",
            type=str,
            choices=[
                "ncbi",
                "kraken2",
                "ganon",
                "ganon2",
                "centrifuge",
                "sylph",
                "diamond",
                "melon",
                "malt",
                "kaiju",
                "metabuli",
                "metacache",
                "mmseqs2",
            ],
            help="Export for specific classifier tool (creates database structure with multiple files)",
        )

        export_group.add_argument(
            "--format",
            "-f",
            type=str,
            choices=[
                "tsv",
                "newick",
                "json",
                "sourmash",
                "accession2taxid",
                "nucl2taxid",
                "prot2taxid",
                "genome_sizes",
                "malt_mapdb",
                "kmcp",
            ],
            help="Export as single file format",
        )

        # Keep old --format for backward compatibility (deprecated)
        parser.add_argument(
            "--legacy-format",
            type=str,
            choices=[
                "ncbi",
                "kraken2",
                "ganon",
                "ganon2",
                "centrifuge",
                "sylph",
                "diamond",
                "melon",
                "malt",
                "kaiju",
                "metabuli",
                "metacache",
                "mmseqs2",
                "tsv",
                "newick",
                "json",
                "sourmash",
                "accession2taxid",
                "nucl2taxid",
                "prot2taxid",
                "genome_sizes",
                "malt_mapdb",
                "kmcp",
            ],
            help=argparse.SUPPRESS,  # Hidden option for backward compatibility
        )

        parser.add_argument(
            "--output",
            "-o",
            type=str,
            required=True,
            help="Output file or directory path",
        )

        parser.add_argument(
            "--include-genomes",
            action="store_true",
            help="Include genome information in export",
        )

        parser.add_argument(
            "--compress", action="store_true", help="Compress output files with gzip"
        )

        # NCBI-specific options
        ncbi_group = parser.add_argument_group("NCBI format options")
        ncbi_group.add_argument(
            "--names-file",
            type=str,
            default="names.dmp",
            help="Name for the names dump file (default: names.dmp)",
        )

        ncbi_group.add_argument(
            "--nodes-file",
            type=str,
            default="nodes.dmp",
            help="Name for the nodes dump file (default: nodes.dmp)",
        )

        # TSV-specific options
        tsv_group = parser.add_argument_group("TSV format options")
        tsv_group.add_argument(
            "--separator",
            type=str,
            default="\t",
            help="Field separator for TSV output (default: tab)",
        )

        # CreateTaxDB-specific options
        createtaxdb_group = parser.add_argument_group("CreateTaxDB format options")
        createtaxdb_group.add_argument(
            "--sequence-filter",
            type=str,
            choices=["all", "nucleotide", "protein"],
            default="all",
            help="Filter sequences by type for nucl2taxid/prot2taxid formats (default: all)",
        )

        createtaxdb_group.add_argument(
            "--default-genome-size",
            type=int,
            default=1000000,
            help="Default genome size when actual size is unknown (default: 1000000)",
        )

        createtaxdb_group.add_argument(
            "--db-version",
            type=str,
            default="1.0",
            help="Database version for MALT MapDB format (default: 1.0)",
        )

        tsv_group.add_argument(
            "--include-header",
            action="store_true",
            default=True,
            help="Include header row in TSV output",
        )

        # New classifier-specific options
        metabuli_group = parser.add_argument_group("Metabuli format options")
        metabuli_group.add_argument(
            "--include-merged",
            action="store_true",
            help="Include merged.dmp file for historical taxonomy changes",
        )

        metacache_group = parser.add_argument_group("MetaCache format options")
        metacache_group.add_argument(
            "--format-type",
            type=str,
            choices=["ncbi_taxonomy", "assembly_summary", "accession2taxid"],
            default="ncbi_taxonomy",
            help="MetaCache export format type (default: ncbi_taxonomy)",
        )

        mmseqs2_group = parser.add_argument_group("MMseqs2 format options")
        mmseqs2_group.add_argument(
            "--sequence-type",
            type=str,
            choices=["all", "protein", "nucleotide"],
            default="all",
            help="Filter sequences by type (default: all)",
        )
        mmseqs2_group.add_argument(
            "--create-lca-mapping",
            action="store_true",
            default=True,
            help="Create LCA-compatible taxonomy mappings (default: True)",
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the export command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)

            # Setup output path
            output_path = Path(args.output)

            # Determine the export type from arguments
            export_type = self._determine_export_type(args)

            # Classify as directory-based (classifiers) or file-based (single files)
            classifier_formats = [
                "ncbi",
                "kraken2",
                "ganon",
                "ganon2",
                "centrifuge",
                "sylph",
                "diamond",
                "melon",
                "malt",
                "kaiju",
                "metabuli",
                "metacache",
                "mmseqs2",
            ]

            if export_type in classifier_formats:
                # Directory-based exports (classifiers)
                self._validate_output_directory(str(output_path), create=True)
            else:
                # File-based exports (single files)
                if output_path.exists() and output_path.is_dir():
                    raise ValidationError(
                        f"Output path is a directory, expected file: {args.output}"
                    )
                # Ensure parent directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

            # Load database and export
            with SQLiteTaxonomyRepository(args.database) as repository:
                tree = repository.load_tree()

                self.logger.info(f"Loaded tree with {tree.node_count} nodes")

                # Route to appropriate export method
                if export_type in classifier_formats or export_type in [
                    "accession2taxid",
                    "nucl2taxid",
                    "prot2taxid",
                    "genome_sizes",
                    "malt_mapdb",
                    "kmcp",
                    "sourmash",
                ]:
                    self._export_classifier_format(tree, output_path, args, export_type)
                elif export_type == "tsv":
                    self._export_tsv(tree, output_path, args)
                elif export_type == "newick":
                    self._export_newick(tree, output_path, args)
                elif export_type == "json":
                    self._export_json(tree, output_path, args)
                else:
                    raise ValidationError(f"Unknown export type: {export_type}")

            print(f"Export completed: {args.output}")
            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1

        except ExportError as e:
            self.logger.error(f"Export error: {e.message}")
            print(f"Export error: {e.message}")
            return 1

    def _determine_export_type(self, args: argparse.Namespace) -> str:
        """Determine the export type from command arguments."""
        # Handle backward compatibility with --legacy-format
        if hasattr(args, "legacy_format") and args.legacy_format:
            return str(args.legacy_format)

        # Use new --classifier or --format options
        if hasattr(args, "classifier") and args.classifier:
            return str(args.classifier)
        elif hasattr(args, "format") and args.format:
            return str(args.format)
        else:
            raise ValidationError("Must specify either --classifier or --format option")

    def _export_classifier_format(
        self,
        tree: TaxonomyTree,
        output_path: Path,
        args: argparse.Namespace,
        export_type: str,
    ) -> None:
        """Export to classifier-specific format using appropriate exporter."""
        from ...exporters.ncbi import NCBIExporter
        from ...exporters.kraken2 import Kraken2Exporter
        from ...exporters.ganon import GanonExporter
        from ...exporters.ganon2 import Ganon2Exporter
        from ...exporters.centrifuge import CentrifugeExporter
        from ...exporters.sylph import SylphExporter
        from ...exporters.diamond import DiamondExporter
        from ...exporters.melon import MelonExporter
        from ...exporters.malt import MALTExporter
        from ...exporters.kaiju import KaijuExporter
        from ...exporters.sourmash import SourmashExporter
        from ...exporters.metabuli import MetabuliExporter
        from ...exporters.metacache import MetaCacheExporter
        from ...exporters.mmseqs2 import MMseqs2Exporter

        # CreateTaxDB compatible exporters
        from ...exporters.accession2taxid import Accession2TaxidExporter
        from ...exporters.nucl2taxid import Nucl2TaxidExporter
        from ...exporters.prot2taxid import Prot2TaxidExporter
        from ...exporters.genome_sizes import GenomeSizesExporter
        from ...exporters.malt_mapdb import MALTMapDBExporter
        from ...exporters.kmcp import KMCPExporter

        # Map format to exporter
        exporters: Dict[str, type[TaxonomyExporter]] = {
            # Standard classifier formats
            "ncbi": NCBIExporter,
            "kraken2": Kraken2Exporter,
            "ganon": GanonExporter,
            "ganon2": Ganon2Exporter,
            "centrifuge": CentrifugeExporter,
            "sylph": SylphExporter,
            "diamond": DiamondExporter,
            "melon": MelonExporter,
            "malt": MALTExporter,
            "kaiju": KaijuExporter,
            "sourmash": SourmashExporter,
            "metabuli": MetabuliExporter,
            "metacache": MetaCacheExporter,
            "mmseqs2": MMseqs2Exporter,
            # CreateTaxDB compatible formats
            "accession2taxid": Accession2TaxidExporter,
            "nucl2taxid": Nucl2TaxidExporter,
            "prot2taxid": Prot2TaxidExporter,
            "genome_sizes": GenomeSizesExporter,
            "malt_mapdb": MALTMapDBExporter,
            "kmcp": KMCPExporter,
        }

        exporter_class = exporters[export_type]
        exporter = exporter_class()

        self.logger.info(f"Exporting to {export_type} format: {output_path}")

        # Prepare export options
        export_options = {
            "compress": args.compress,
            "include_genomes": args.include_genomes,
            "names_file": args.names_file,
            "nodes_file": args.nodes_file,
            # CreateTaxDB format options
            "sequence_filter": getattr(args, "sequence_filter", "all"),
            "default_genome_size": getattr(args, "default_genome_size", 1000000),
            "db_version": getattr(args, "db_version", "1.0"),
            # New classifier options
            "include_merged": getattr(args, "include_merged", False),
            "format_type": getattr(args, "format_type", "ncbi_taxonomy"),
            "sequence_type": getattr(args, "sequence_type", "all"),
            "create_lca_mapping": getattr(args, "create_lca_mapping", True),
        }

        # Export using the appropriate exporter
        exporter.export(tree, output_path, **export_options)

        print(f"Created {export_type} taxonomy files in: {output_path}")

        # Show what was created
        created_files = list(output_path.glob("*"))
        for file_path in sorted(created_files):
            if file_path.is_file():
                print(f"  {file_path.name}")

        # Show subdirectories
        created_dirs = [p for p in created_files if p.is_dir()]
        for dir_path in sorted(created_dirs):
            print(f"  {dir_path.name}/")
            sub_files = list(dir_path.glob("*"))
            for sub_file in sorted(sub_files):
                if sub_file.is_file():
                    print(f"    {sub_file.name}")

    def _export_tsv(
        self, tree: TaxonomyTree, output_path: Path, args: argparse.Namespace
    ) -> None:
        """Export to TSV format."""
        self.logger.info(f"Exporting to TSV format: {output_path}")

        with open(output_path, "w") as f:
            if args.include_header:
                f.write(f"parent{args.separator}child{args.separator}rank\n")

            for node in tree:
                if node.parent_id is not None:
                    parent_node = tree.get_node(node.parent_id)
                    parent_name = (
                        parent_node.name if parent_node else str(node.parent_id)
                    )
                    f.write(
                        f"{parent_name}{args.separator}{node.name}{args.separator}{node.rank.value}\n"
                    )

        if args.compress:
            from ...utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _export_newick(
        self, tree: TaxonomyTree, output_path: Path, args: argparse.Namespace
    ) -> None:
        """Export to Newick tree format."""
        self.logger.info(f"Exporting to Newick format: {output_path}")

        # Simple Newick export (this is a basic implementation)
        def build_newick(node_id: int) -> str:
            node = tree.get_node(node_id)
            if not node:
                return ""

            children = tree.get_children(node_id)
            if not children:
                return node.name

            child_strings = [build_newick(child_id) for child_id in children]
            return f"({','.join(child_strings)}){node.name}"

        root_id = tree.root_id
        if root_id is None:
            raise ExportError("Cannot export to Newick: no root node found")

        newick_string = build_newick(root_id) + ";"

        with open(output_path, "w") as f:
            f.write(newick_string + "\n")

        if args.compress:
            from ...utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _export_json(
        self, tree: TaxonomyTree, output_path: Path, args: argparse.Namespace
    ) -> None:
        """Export to JSON format."""
        import json

        self.logger.info(f"Exporting to JSON format: {output_path}")

        # Build tree structure
        nodes_data = []
        for node in tree:
            node_data = {
                "tax_id": node.tax_id,
                "name": node.name,
                "rank": node.rank.value,
                "parent_id": node.parent_id,
            }

            if args.include_genomes:
                genomes = tree.get_genomes_for_node(node.tax_id)
                node_data["genomes"] = [
                    {
                        "genome_id": g.genome_id,
                        "file_path": g.file_path,
                        "assembly_accession": g.assembly_accession,
                        "source": g.source,
                    }
                    for g in genomes
                ]

            nodes_data.append(node_data)

        export_data = {
            "metadata": {
                "format_version": "1.0",
                "node_count": tree.node_count,
                "genome_count": tree.genome_count,
                "root_id": tree.root_id,
            },
            "nodes": nodes_data,
        }

        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        if args.compress:
            from ...utils.subprocess_utils import compress_file

            compress_file(output_path)
