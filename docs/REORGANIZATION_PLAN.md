# Test Reorganization Plan

## Current Issues
- 5 duplicated exporter test files (2,854 total lines)
- Integration tests scattered across locations  
- Poor naming and unclear organization
- Tests don't mirror source code structure

## New Structure

```
tests/
├── unit/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_models.py           # TaxonomyTree, TaxonomyNode, etc.
│   │   ├── test_exceptions.py       # All custom exceptions
│   │   └── test_tree_operations.py  # Advanced tree operations
│   │
│   ├── parsers/
│   │   ├── __init__.py
│   │   └── test_parsers.py          # Already well organized, keep as-is
│   │
│   ├── exporters/
│   │   ├── __init__.py
│   │   ├── test_base_exporters.py      # Base classes and interfaces
│   │   ├── test_classic_exporters.py   # NCBI, Kraken2, Ganon, Centrifuge
│   │   ├── test_createtaxdb_exporters.py # accession2taxid, nucl2taxid, etc.
│   │   └── test_modern_exporters.py    # Metabuli, MetaCache, MMseqs2
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── test_commands.py         # All CLI commands
│   │   └── test_architecture.py     # CLI structure and new format
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   └── test_sqlite_repository.py # Database operations
│   │
│   └── utils/
│       ├── __init__.py
│       ├── test_logging.py
│       ├── test_subprocess.py
│       └── test_sequence_utils.py
│
├── integration/
│   ├── __init__.py  
│   ├── test_end_to_end_workflows.py    # Complete create->export workflows
│   ├── test_cli_integration.py         # CLI integration tests
│   └── test_format_compatibility.py    # Cross-format compatibility
│
└── performance/
    ├── __init__.py
    ├── test_benchmarks.py              # Performance benchmarks
    └── test_memory_optimization.py     # Memory usage tests
```

## Consolidation Plan

### Files to Merge:
- `test_exporters.py` + `test_exporters_fixed.py` + individual exporter tests → organized exporter modules
- All integration tests → `/integration/` directory
- Generic utility tests → organized `/utils/` modules

### Files to Remove:
- `test_exporters.py` (superseded)  
- `test_metabuli_exporter.py` (consolidate)
- `test_metacache_exporter.py` (consolidate)
- `test_mmseqs2_exporter.py` (consolidate)
- Root-level integration tests (move)
- `test_fixtures.py` (integrate into relevant modules)

### Benefits:
- Eliminate ~1,500 lines of duplication
- Clear structure mirroring source code
- Easy to find relevant tests
- Better maintainability
- Consistent naming conventions