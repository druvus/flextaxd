# FlexTaxD Documentation

Welcome to the FlexTaxD documentation. This directory contains guides and references for using and developing with FlexTaxD.

## Documentation Structure

### Getting Started  
- [**Installation**](installation.md) - Installation instructions
- [**Quick Start**](quick-start.md) - Basic usage examples
- [**User Guide**](user-guide.md) - Comprehensive usage guide
- [**CLI Reference**](cli-reference.md) - Command-line interface documentation

### Features & Formats
- [**Format Support**](formats.md) - Input and export format specifications
- [**Classification Tools**](classification.md) - Export formats for taxonomic classifiers
- [**Pipeline Integration**](pipeline-integration.md) - Integration with bioinformatics workflows

### Development
- [**Developer Guide**](development.md) - Contributing and extending FlexTaxD
- [**Architecture Overview**](architecture.md) - System design and components
- [**Testing Guide**](testing.md) - Test suite information
- [**Technical Reference**](../CLAUDE.md) - Development guidance and current status

### Reference
- [**Troubleshooting**](troubleshooting.md) - Common issues and solutions
- [**FAQ**](faq.md) - Frequently asked questions

### Technical Documentation
- [**Strategic Improvement Plan**](FLEXTAXD_STRATEGIC_IMPROVEMENT_PLAN.md) - Development roadmap
- [**Refactoring Summary**](REFACTORING_SUMMARY.md) - Architecture improvements

## Quick Navigation

| I want to... | Go to... |
|---------------|----------|
| Install FlexTaxD | [Installation](installation.md) |
| Start using FlexTaxD | [Quick Start](quick-start.md) |
| Export for classification tools | [Classification Tools](classification.md) |
| Integrate with pipelines | [Pipeline Integration](pipeline-integration.md) |
| Extend or contribute | [Developer Guide](development.md) |
| Solve problems | [Troubleshooting](troubleshooting.md) |
| View technical status | [Technical Reference](../CLAUDE.md) |
| See development roadmap | [Strategic Plan](FLEXTAXD_STRATEGIC_IMPROVEMENT_PLAN.md) |

## FlexTaxD Overview

### Core Features
- **Modern CLI design**: Intuitive --classifier/--format distinction for exports
- **22+ export formats**: Support for major bioinformatics classification tools
- **6 input parsers**: TSV, NCBI, GTDB, QIIME, CanSNPer, SILVA formats
- **Database management**: SQLite-based storage with modification support
- **Visualization**: Tree plots and Newick format export (requires BioPython)

### CLI Design (2024 Update)
FlexTaxD uses a clear separation for exports:
- **`--classifier`**: Tools that create database structures (Kraken2, Diamond, Metabuli, etc.)
- **`--format`**: Single file exports (TSV, JSON, accession2taxid, etc.)

### Supported Classification Tools
- **Kraken2/Bracken**: Metagenomic classification
- **Diamond**: Protein sequence alignment
- **Ganon/Ganon2**: Hierarchical classification
- **Sourmash**: k-mer profiling
- **Sylph**: Genome sketching  
- **Kaiju**: NCBI-compliant protein classification
- **MALT**: MEGAN alignment tool
- **Metabuli**: Modern NCBI-style format (NEW)
- **MetaCache**: Multiple format support (NEW)
- **MMseqs2**: Enhanced NCBI format (NEW)

### Quality Status
- **Test coverage**: Core functionality tested
- **Type annotations**: Present throughout codebase  
- **Modular architecture**: Plugin-based parsers and exporters
- **Active development**: Regular updates and improvements

## Basic Usage Examples

### Database Creation
```bash
# Create from different input formats
flextaxd create --input taxonomy.tsv --format tsv --database my_db.ftd
flextaxd create --input ncbi_dump/ --format ncbi --database ncbi.ftd
flextaxd create --input gtdb_taxonomy.tsv --format gtdb --database gtdb.ftd
```

### Export Examples
```bash
# Export to classifier tools (creates directory structures)
flextaxd export --database my_db.ftd --classifier kraken2 --output kraken2_db/
flextaxd export --database my_db.ftd --classifier metabuli --output metabuli_db/

# Export to single file formats
flextaxd export --database my_db.ftd --format tsv --output taxonomy.tsv
flextaxd export --database my_db.ftd --format accession2taxid --output acc2taxid.txt
```

## Getting Help

- **CLI help**: `flextaxd --help` and `flextaxd [command] --help`
- **Technical reference**: See [CLAUDE.md](../CLAUDE.md) for current development status
- **Issues**: Report problems via GitHub issues
- **Contributing**: See [Developer Guide](development.md)

---

**FlexTaxD** - Modern taxonomy database management for bioinformatics workflows