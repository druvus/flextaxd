# FlexTaxD - Flexible Taxonomy Database Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

**FlexTaxD** is a bioinformatics tool for creating, customizing, and managing taxonomy databases from diverse sources. It provides a modern CLI interface with clear separation between classifier tools and file formats, supporting major taxonomic classification workflows.

## Features

### Format Support
**Input Formats:**
- **NCBI**: Taxonomy dump format (names.dmp, nodes.dmp)
- **GTDB**: Genome Taxonomy Database files (ar122/bac120)
- **QIIME**: Semicolon-delimited hierarchies
- **TSV**: Tab-separated values (generic format)
- **CanSNPer**: Phylogenetic SNP classification format
- **SILVA**: rRNA database formats

**Export Options:**
- **Classifier tools** (--classifier): Creates database structures for classification software
- **File formats** (--format): Exports single files in specific formats

### CLI Design
The export command uses an intuitive structure:
- `--classifier`: For tools that need database structures (Kraken2, Diamond, etc.)
- `--format`: For single file exports (TSV, JSON, accession2taxid, etc.)

### Core Functionality
- **Database creation**: From multiple input formats with auto-detection
- **Database modification**: Add, update, and remove taxonomic nodes
- **Statistics and analysis**: Database metrics and information
- **Visualization**: Tree plots and Newick format export (requires BioPython)
- **Pipeline integration**: Compatible with nf-core and other workflows

## Quick Start

### Installation
```bash
# Development installation (recommended)
pip install -e ".[dev]"

# Production installation  
pip install .

# Install with visualization support
pip install ".[visualization]"  # Requires BioPython and matplotlib
```

### Basic Usage

#### Database Creation
```bash
# Create database from NCBI taxonomy
flextaxd create --input taxdump/ --format ncbi --database ncbi.ftd

# Create from GTDB format  
flextaxd create --input gtdb_taxonomy.tsv --format gtdb --database gtdb.ftd

# Create from custom TSV
flextaxd create --input custom.tsv --format tsv --database custom.ftd
```

#### Export Examples
```bash
# Export to classifier tools (creates directory structures)
flextaxd export --database gtdb.ftd --classifier kraken2 --output kraken2_db/
flextaxd export --database gtdb.ftd --classifier diamond --output diamond_db/
flextaxd export --database gtdb.ftd --classifier metabuli --output metabuli_db/

# Export to single file formats
flextaxd export --database gtdb.ftd --format tsv --output taxonomy.tsv
flextaxd export --database gtdb.ftd --format accession2taxid --output acc2taxid.txt
flextaxd export --database gtdb.ftd --format json --output taxonomy.json
```

#### Database Management
```bash
# Database statistics
flextaxd stats --database gtdb.ftd --detailed

# Add custom nodes
flextaxd modify --database gtdb.ftd --add-node "Custom Species" --parent-id 562 --rank species

# Visualize taxonomy (requires BioPython)
flextaxd visualize --database gtdb.ftd --type tree --output tree.png
```

## Bioinformatics Integration

### Classification Tool Workflows

**Kraken2 & Bracken:**
```bash
# Export FlexTaxD database for Kraken2
flextaxd export --database db.ftd --classifier kraken2 --output kraken2_db/

# Build and run Kraken2 (requires genome sequences)
kraken2-build --add-to-library sequences.fasta --db kraken2_db/
kraken2-build --build --db kraken2_db/
kraken2 --db kraken2_db/ --threads 8 reads.fastq > results.kraken
```

**Diamond:**
```bash
# Export for Diamond
flextaxd export --database db.ftd --classifier diamond --output diamond_db/

# Use with Diamond (requires protein sequences)
diamond makedb --in proteins.fasta --db diamond_db/proteins
diamond blastx --db diamond_db/proteins --query reads.fastq --out results.tsv
```

**Modern Tools:**
```bash
# Metabuli (modern NCBI-style format)
flextaxd export --database db.ftd --classifier metabuli --output metabuli_db/

# MetaCache (multiple format support)  
flextaxd export --database db.ftd --classifier metacache --output metacache_db/

# MMseqs2 (enhanced NCBI format)
flextaxd export --database db.ftd --classifier mmseqs2 --output mmseqs2_db/
```

**k-mer Based Tools:**
```bash
# Sourmash
flextaxd export --database db.ftd --classifier sourmash --output sourmash_db/

# Sylph
flextaxd export --database db.ftd --classifier sylph --output sylph_db/
```

### Pipeline Integration

**nf-core/createtaxdb Compatible Files:**
```bash
# Export single file formats for nf-core pipeline
flextaxd export --database db.ftd --format accession2taxid --output accession2taxid.txt
flextaxd export --database db.ftd --format nucl2taxid --output nucl2taxid.txt
flextaxd export --database db.ftd --format prot2taxid --output prot2taxid.txt
flextaxd export --database db.ftd --format genome_sizes --output genome_sizes.txt

# Use with nf-core/createtaxdb pipeline
nextflow run nf-core/createtaxdb \
    --accession2taxid accession2taxid.txt \
    --nucl2taxid nucl2taxid.txt \
    --genome_sizes genome_sizes.txt
```

**Generic File Exports:**
```bash
# Data exchange formats
flextaxd export --database db.ftd --format tsv --output taxonomy.tsv
flextaxd export --database db.ftd --format json --output taxonomy.json
flextaxd export --database db.ftd --format newick --output tree.nwk
```

## Architecture

### Code Organization
```
flextaxd/
├── cli/                    # Command-line interface
│   ├── commands/          # Individual CLI commands 
│   └── main.py           # Main entry point
├── core/                   # Core data structures
│   ├── models.py          # TaxonomyTree, TaxonomyNode classes
│   ├── exceptions.py      # Error handling
│   └── [advanced modules] # Performance features (limited testing)
├── parsers/               # Input format parsers (6 formats)
├── database/              # SQLite storage operations  
├── exporters/             # Output format exporters (22+ formats)
└── utils/                 # Support utilities
```

### Database Features
- **SQLite storage**: Reliable database backend with ACID compliance
- **Flexible schema**: Support for diverse taxonomic hierarchies
- **Node operations**: Add, update, and remove taxonomic nodes
- **Statistics**: Database metrics and analysis
- **Export options**: Multiple output formats for different tools

### Quality Metrics
- **Test coverage**: Core functionality tested, some advanced features need validation
- **Type annotations**: Present throughout codebase with some remaining MyPy issues
- **Modular design**: Plugin-based architecture for parsers and exporters
- **CLI design**: Intuitive --classifier/--format distinction for exports
- **Documentation**: Comprehensive CLI help and usage examples

## Use Cases

### Research Applications
- **Custom taxonomies**: Build specialized databases for specific research domains
- **Format conversion**: Convert between different taxonomy formats
- **Database curation**: Maintain and update taxonomic classifications
- **Pipeline integration**: Incorporate into bioinformatics workflows

### Supported Workflows
- **Metagenomics**: Export databases for Kraken2, Ganon, Centrifuge
- **Protein analysis**: Create databases for Diamond, Kaiju, MALT
- **k-mer profiling**: Generate databases for Sourmash, Sylph
- **Modern tools**: Support for Metabuli, MetaCache, MMseqs2

## Development

### Testing
```bash
# Run core tests (recommended)
pytest tests/unit/test_parsers.py -v          # Parser functionality
pytest tests/unit/test_exporters.py -v        # Export functionality
pytest tests/unit/test_cli_architecture.py -v # CLI tests

# Type checking (has some remaining issues)
mypy flextaxd/ --ignore-missing-imports

# Code formatting
black flextaxd/ tests/

# Linting
ruff check flextaxd/ tests/
```

### Contributing Guidelines
- **Testing**: Add tests for new functionality
- **Documentation**: Update CLI help and examples
- **Type safety**: Maintain type annotations where possible
- **Code quality**: Follow existing formatting standards

## Documentation

### Command Reference
```bash
# Comprehensive help system
flextaxd --help                    # Main help
flextaxd create --help             # Database creation
flextaxd export --help             # Export formats
flextaxd modify --help             # Database modifications
flextaxd stats --help              # Database statistics  
flextaxd visualize --help          # Tree visualization
```

### Additional Resources
- **CLAUDE.md**: Detailed format documentation and examples
- **Wiki pages**: Comprehensive guides for input/output formats
- **CLI help**: Built-in documentation for all commands and options

## Citation

If you use FlexTaxD in your research, please cite:

```bibtex
@article{sundell2021flextaxd,
  title={FlexTaxD: flexible modification of taxonomy databases for improved sequence classification},
  author={Sundell, David and others},
  journal={Bioinformatics},
  year={2021},
  doi={10.1093/bioinformatics/btab621}
}
```

## License

FlexTaxD is open source software licensed under the [MIT License](LICENSE).

---

**FlexTaxD** - Modern taxonomy database management with intuitive CLI design and comprehensive format support for bioinformatics workflows.