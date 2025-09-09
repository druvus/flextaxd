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
- [**Test Reorganization Plan**](REORGANIZATION_PLAN.md) - Test suite reorganization strategy
- [**Test Reorganization Report**](REORGANIZATION_COMPLETED.md) - Completed test suite improvements

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

FlexTaxD is a bioinformatics tool for creating, managing, and exporting taxonomy databases. The software supports multiple input formats and provides export capabilities for integration with classification tools and analysis pipelines.

### Core Features
- Input format support with automated format detection (6 parsers)
- Export functionality for classification tools and data formats (22+ formats)
- SQLite database backend with transaction support
- Multi-level validation system for data integrity
- Structured command-line interface with comprehensive help
- Visualization capabilities and statistics reporting

### CLI Design (2024 Update)
FlexTaxD uses a clear separation for exports:
- **`--classifier`**: Tools that create database structures (Kraken2, Diamond, Metabuli, etc.)
- **`--format`**: Single file exports (TSV, JSON, accession2taxid, etc.)

### Classification Tools Support (22+ Formats)

FlexTaxD provides export functionality for the following tool categories:

#### Directory-Based Classifiers (`--classifier`)
- **Kraken2/Bracken**: Metagenomic classification
- **Diamond**: Protein sequence alignment databases
- **Ganon/Ganon2**: Hierarchical classification formats
- **Sourmash**: k-mer-based profiling databases
- **Sylph**: Genome sketching format  
- **Kaiju**: NCBI-compliant protein classification
- **MALT**: MEGAN alignment tool format
- **Metabuli**: Modern NCBI-style with merged taxonomy
- **MetaCache**: Multiple format types (ncbi_taxonomy, assembly_summary)
- **MMseqs2**: Enhanced NCBI format with LCA mappings
- **Centrifuge**: Compressed suffix array format
- **Melon**: Long-read taxonomic profiling

#### Single File Formats (`--format`) 
- **TSV/JSON**: Structured data formats
- **Newick**: Phylogenetic tree format
- **accession2taxid/nucl2taxid/prot2taxid**: NCBI-style sequence mappings
- **genome_sizes**: Genome size annotations
- **And many more...**

### Implementation Status
- Test infrastructure: Recently stabilized through systematic debugging
- Modular architecture with extensible parsers and exporters
- Type annotations and error handling throughout codebase
- SQLite database backend with transaction support
- Validation and logging frameworks implemented
- Command-line interface with comprehensive help documentation

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

**FlexTaxD** - Taxonomy database management for bioinformatics workflows