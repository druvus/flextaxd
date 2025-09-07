# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the FlexTaxD repository.

## Overview

FlexTaxD is a **production-ready bioinformatics tool** for creating, customizing, and managing taxonomy databases from diverse sources. It provides comprehensive format support, modern CLI design, and robust database operations for bioinformatics workflows.

## Current Status (2025-09-07)

### ✅ **Completed Features**

#### **Core Functionality**
- **Database Creation**: Support for 6+ input formats (NCBI, GTDB, TSV, QIIME, SILVA, CanSNPer)
- **Export System**: 22+ classification tool formats (most comprehensive in the field)
- **Visualization**: Tree, plot, and Newick format outputs
- **Statistics**: Detailed database analysis with file validation
- **NCBI Integration**: Direct download via NCBI Datasets API

#### **Recent Enhancements (Phase 4 Completed)**
- ✅ **Accession-based download system** with flat file structure by default
- ✅ **MD5 checksum storage** in database for integrity verification  
- ✅ **Clean metadata management** - automatic removal of NCBI clutter
- ✅ **Enhanced status reporting** with visual indicators
- ✅ **Path cleaning** for orphaned file references

### ⚠️ **Known Issues & Limitations**

#### **Test Coverage (Critical Issue)**
- **Overall coverage**: 13% (981 tests collected)
- **Missing tests for**: download, assign_accessions, export_mappings, import_accessions, register commands
- **Zero coverage**: All validation modules, sequence tracking

#### **Code Organization Issues**
- **Orphaned code**: ~2000 lines never used (high_performance modules, adaptive_cache, etc.)
- **Deprecated files**: modify.py.deprecated still present
- **Duplicate validation**: Multiple overlapping validation systems
- **Command proliferation**: 20+ commands may overwhelm users

#### **Documentation Gaps**
- **Wiki outdated**: References deprecated modify command
- **Missing walkthroughs**: New download workflow, accession operations
- **Inconsistent examples**: Some use old parameter names

### 🎯 **Immediate Priorities**

1. **Increase test coverage** to >80% for critical paths
2. **Remove orphaned code** (~2000 lines)
3. **Update documentation** to match current implementation
4. **Consolidate validation** into single coherent system
5. **Restore modify command** or update all references

## 📋 **Command Reference**

### **Database Operations**
```bash
flextaxd create        # Create taxonomy database
flextaxd stats         # Display statistics
flextaxd validate      # Validate integrity
flextaxd purge         # Remove nodes without data
```

### **Data Management**
```bash
flextaxd import-accessions  # Import accession mappings
flextaxd download          # Download by accession
flextaxd register          # Register sequence files
flextaxd list-missing      # List missing files
```

### **Export & Visualization**
```bash
flextaxd export           # Export to classification tools
flextaxd export-mappings  # Export mapping files
flextaxd visualize        # Generate visualizations
```

### **Node Management**
```bash
flextaxd add-node      # Add single node
flextaxd add-genome    # Add genome to node
flextaxd import-tree   # Import taxonomy tree
```

## 🏗️ **Architecture**

```
flextaxd/
├── cli/                  # Command-line interface
│   └── commands/         # 20+ subcommands
├── core/                 # Core data structures
│   ├── models.py         # TaxonomyTree, TaxonomyNode, GenomeInfo
│   └── *.py             # (orphaned performance modules to remove)
├── parsers/              # Input format parsers
│   └── [6 format parsers]
├── exporters/            # Output format exporters  
│   └── [22+ exporters]
├── database/             # Database operations
│   └── sqlite.py         # Main database layer
├── validation/           # Validation modules (needs consolidation)
├── sequence/             # Sequence tracking (new)
└── utils/                # Utility functions
```

## 🔧 **Development Guidelines**

### **When Adding Features**
1. **Check for existing functionality** - avoid duplication
2. **Add tests** - maintain >80% coverage for new code
3. **Update documentation** - keep wiki and help text current
4. **Use type hints** - maintain type safety
5. **Follow patterns** - consistency with existing code

### **Testing Requirements**
```bash
# Run tests before commits
pytest tests/unit/        # Unit tests
pytest tests/integration/ # Integration tests
mypy flextaxd/           # Type checking
ruff check flextaxd/     # Linting
```

### **Common Patterns**
```python
# Database operations
repository = SQLiteTaxonomyRepository(database_path)
tree = repository.get_tree()

# Command structure
class MyCommand(BaseCommand):
    @staticmethod
    def register_args(parser):
        # Add arguments
    
    def execute(self, args):
        # Implementation

# Error handling
try:
    # Operation
except ValidationError as e:
    logger.error(f"Validation failed: {e}")
    return 1
```

## 📊 **Performance Considerations**

### **Current Limitations**
- Single-threaded operations (except download)
- Memory-intensive tree operations for large taxonomies
- SQLite concurrent write limitations

### **Optimization Opportunities**
- Add multiprocessing for batch operations
- Implement streaming parsers for large files
- Consider PostgreSQL for large deployments
- Add progress bars for long operations

## 🚨 **Critical Code Sections**

### **Database Schema**
- `flextaxd/database/sqlite.py`: Main database operations
- Schema includes: nodes, genomes, accession_mappings tables
- Recent addition: file_checksum column for integrity

### **Core Models**
- `flextaxd/core/models.py`: Data structures
- Key classes: TaxonomyNode, GenomeInfo, TaxonomyTree
- Recent addition: file_checksum field in GenomeInfo

### **Download System**
- `flextaxd/cli/commands/download.py`: Accession-based downloads
- `flextaxd/utils/ncbi_datasets.py`: NCBI integration
- Features: flat file structure, MD5 tracking, metadata cleanup

## 🐛 **Known Bugs**

1. **modify command deprecated** but still referenced in documentation
2. **Test failures** in visualization and modify command tests
3. **Orphaned imports** causing unnecessary dependencies
4. **Inconsistent logging** between modules

## 📝 **Documentation Status**

### **Up-to-date**
- Basic usage examples
- Export format descriptions
- Database creation workflows

### **Needs Update**
- Wiki walkthroughs (reference deprecated commands)
- Accession-based workflow documentation
- Validation system documentation
- Performance tuning guide

## 🎯 **Future Enhancements**

### **High Priority**
1. Consolidate validation systems
2. Restore modify command functionality
3. Add comprehensive test suite
4. Update all documentation

### **Medium Priority**
1. Add progress indicators
2. Implement parallel processing
3. Add database versioning
4. Create GUI interface

### **Low Priority**
1. PostgreSQL support
2. Cloud storage integration
3. REST API
4. Docker containerization

## 💡 **Tips for Development**

1. **Start with tests** - Write tests before implementation
2. **Use existing patterns** - Follow established code structure
3. **Document changes** - Update help text and wiki
4. **Check performance** - Profile large operations
5. **Validate inputs** - Never trust user data

## 🔄 **Migration Notes**

### **From Old to New CLI**
- `flextaxd-create` → `flextaxd create`
- `flextaxd-modify` → deprecated (use add-node, import-tree)
- Parameters now use `--` prefix consistently

### **Database Compatibility**
- Databases created with older versions are compatible
- New file_checksum column added automatically
- Backup before major operations recommended

## 📚 **Resources**

- **GitHub**: https://github.com/FOI-Bioinformatics/flextaxd
- **Wiki**: Available in repository wiki section
- **Test Data**: wiki/example_data directory
- **Support**: Create GitHub issues for bugs/features