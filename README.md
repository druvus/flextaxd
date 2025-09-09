# FlexTaxD - Taxonomy Database Management Tool

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/Tests-Infrastructure_Stabilized-green.svg)](#testing)
[![Code Coverage](https://img.shields.io/badge/Coverage-Improving-yellow.svg)](#testing)

FlexTaxD is a bioinformatics tool for creating, customizing, and managing taxonomy databases from diverse sources. The tool supports multiple input formats and provides extensive export capabilities for major classification tools used in bioinformatics workflows.

## Key Features

### Format Support
- **Input Formats**: 6 parsers supporting NCBI, GTDB, TSV, QIIME, SILVA, CanSNPer
- **Export Formats**: 22+ output formats for classification tools
- **Classification Tools**: Kraken2, Diamond, Metabuli, MMseqs2, and additional tools
- **Mapping Files**: Standard formats including accession2taxid, nucl2taxid, prot2taxid, genome_sizes

### Architecture
- **Database Backend**: SQLite with ACID compliance and transaction support
- **Modular Design**: Extensible architecture for parsers and exporters
- **Type Safety**: Python 3.11+ with type annotations
- **Command Interface**: Structured subcommands with comprehensive help documentation

### Capabilities
- **NCBI Integration**: Direct download functionality via NCBI Datasets API
- **Accession Management**: Precise genome control through accession-based operations
- **Data Validation**: Multi-level validation including MD5 checksum verification
- **Visualization**: Multiple output formats including tree, plot, and Newick representations

## 📦 Installation

### **Standard Installation**
```bash
# Basic installation
pip install flextaxd

# With visualization support
pip install "flextaxd[visualization]"

# Development installation
pip install -e ".[dev]"
```

### **Requirements**
- Python 3.11 or later
- SQLite3 (included with Python)
- Optional: BioPython for visualization
- Optional: NCBI Datasets CLI for genome downloads

## 🚀 Quick Start

### **Create Database**
```bash
# From TSV file
flextaxd create --input taxonomy.tsv --database my_db.ftd

# From NCBI taxonomy dump
flextaxd create --input ncbi_dump/ --format ncbi --database ncbi.ftd

# From GTDB
flextaxd create --input gtdb_taxonomy.tsv --format gtdb --database gtdb.ftd

# Direct from NCBI Datasets (downloads taxonomy automatically)
flextaxd create --ncbi-datasets "Escherichia coli" --database ecoli.ftd
```

### **Export for Classification Tools**
```bash
# Kraken2 database (creates directory structure)
flextaxd export --database my_db.ftd --classifier kraken2 --output kraken2_db/

# Diamond protein database
flextaxd export --database my_db.ftd --classifier diamond --output diamond_db/

# Standard mapping files
flextaxd export-mappings --database my_db.ftd --format accession2taxid --output acc2taxid.txt
```

### **Download Genomes**
```bash
# Download missing genomes (flat file structure by default)
flextaxd download --database my_db.ftd --missing --type genome --output-dir genomes/

# Download specific accessions
flextaxd download --database my_db.ftd --accessions GCF_000005825.2,GCF_000009605.1 --output-dir data/

# Clean paths for missing files
flextaxd download --database my_db.ftd --clean-missing-paths
```

### **Database Management**
```bash
# View statistics
flextaxd stats --database my_db.ftd --detailed

# Validate integrity
flextaxd validate --database my_db.ftd --level comprehensive

# Add nodes
flextaxd add-node --database my_db.ftd --name "New Species" --parent-id 12345 --rank species

# Visualize
flextaxd visualize --database my_db.ftd --type tree --output tree.png

# Remove nodes without data
flextaxd purge --database my_db.ftd --backup backup.ftd
```

## 📋 Command Reference

### **Core Commands**
| Command | Description |
|---------|-------------|
| `create` | Create taxonomy database from various sources |
| `export` | Export to classification tools |
| `export-mappings` | Export standard mapping files |
| `stats` | Display database statistics |
| `validate` | Validate database integrity |

### **Data Management**
| Command | Description |
|---------|-------------|
| `import-accessions` | Import accession-to-taxonomy mappings |
| `download` | Download genomes by accession |
| `register` | Register sequence files |
| `list-missing` | List missing files |
| `validate-files` | Validate file integrity |

### **Node Operations**
| Command | Description |
|---------|-------------|
| `add-node` | Add single taxonomy node |
| `add-genome` | Add genome to node |
| `import-tree` | Import taxonomy tree |
| `assign-accessions` | Auto-assign accessions |

### **Visualization & Analysis**
| Command | Description |
|---------|-------------|
| `visualize` | Generate tree visualizations |
| `purge` | Remove nodes without data |

## 🔬 Supported Formats

### **Input Formats**
- **NCBI**: Standard taxonomy dump (names.dmp, nodes.dmp)
- **GTDB**: Genome Taxonomy Database format
- **TSV**: Tab-separated values with flexible columns
- **QIIME**: Semicolon-delimited hierarchies
- **SILVA**: rRNA database formats
- **CanSNPer**: Phylogenetic SNP classification

### **Export Formats (--classifier)**
**Metagenomic Classification:**
- Kraken2, Centrifuge, Ganon/Ganon2

**Protein Analysis:**
- Diamond, Kaiju, MALT, MMseqs2

**Modern Tools:**
- Metabuli, MetaCache, Sourmash, Sylph

**Standard Format:**
- NCBI (names.dmp/nodes.dmp)

### **Single File Formats (--format)**
- TSV, JSON, Newick
- accession2taxid, nucl2taxid, prot2taxid
- genome_sizes, malt_mapdb, kmcp

## Testing

```bash
# Execute unit tests
pytest tests/unit/

# Execute integration tests
pytest tests/integration/

# Generate coverage report
pytest --cov=flextaxd tests/

# Type checking
mypy flextaxd/

# Code linting
ruff check flextaxd/
```

**Current Status:**
- Test infrastructure: Recently stabilized through systematic debugging
- Critical test failures: Resolved through 4-phase improvement approach
- Test suite: Foundation established for continued development
- Coverage expansion: Ongoing development priority

## Performance

### Scalability
- Supports databases containing large numbers of taxonomic nodes
- SQLite backend with transaction optimization
- Streaming functionality for large file processing

### Current Limitations
- Primarily single-threaded operations (download operations support concurrency)
- Memory requirements scale with tree complexity
- SQLite backend limits concurrent write operations

## Current Issues

1. **Code organization**: Orphaned modules require cleanup (~2000 lines)
2. **Command deprecation**: modify command deprecated, alternative commands available
3. **Documentation maintenance**: Some references require updates for current functionality
4. **Test coverage**: Expansion ongoing for newer command implementations

## Contributing

Contributions are welcome. Please follow these guidelines:
1. Fork the repository and create a feature branch
2. Implement tests for new functionality
3. Update relevant documentation
4. Ensure code follows existing patterns and style
5. Submit a pull request with clear description of changes

## 📝 Documentation

- **Wiki**: [GitHub Wiki](https://github.com/FOI-Bioinformatics/flextaxd/wiki)
- **Examples**: See `wiki/example_data/` directory
- **API Docs**: In-code documentation

## 🏢 Use Cases

### **Research Applications**
- Custom taxonomy databases for specific clades
- Integration of public and private genome data
- Comparative genomics workflows

### **Clinical Diagnostics**
- Pathogen detection databases
- Strain-level identification
- AMR gene tracking

### **Metagenomics**
- Environmental sample analysis
- Microbiome studies
- Custom database curation

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- FOI Swedish Defence Research Agency
- Contributors and users of FlexTaxD
- Bioinformatics community

## 📧 Support

- **Issues**: [GitHub Issues](https://github.com/FOI-Bioinformatics/flextaxd/issues)
- **Discussions**: [GitHub Discussions](https://github.com/FOI-Bioinformatics/flextaxd/discussions)

## 🔗 Links

- **GitHub**: https://github.com/FOI-Bioinformatics/flextaxd
- **PyPI**: https://pypi.org/project/flextaxd/ (when published)

---

**Note**: FlexTaxD continues to evolve with ongoing development. Database backup is recommended before performing major operations to ensure data preservation.