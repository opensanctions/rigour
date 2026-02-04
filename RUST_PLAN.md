# Rust Migration Plan for Rigour

## Executive Summary

This document outlines a phased approach to migrating performance-critical components of the rigour library from Python to Rust, while maintaining 100% API compatibility. The migration will use PyO3 for Python bindings and maturin for build integration. Rust becomes a hard requirement, just like the existing Rust-based dependencies (`rapidfuzz`, `orjson`, `ahocorasick-rs`).

## Goals

1. **Performance**: Achieve 5-10x speedup on hot-path functions (normalization, string comparison, tokenization)
2. **Memory Efficiency**: Reduce memory overhead for large-scale batch processing
3. **API Compatibility**: Maintain 100% API compatibility - existing code continues to work unchanged
4. **Simplicity**: Single implementation (Rust), no Python fallbacks to maintain
5. **Type Safety**: Leverage Rust's type system for correctness guarantees
6. **Developer Experience**: Seamless installation via pre-built wheels for all major platforms

## Architecture

### Rust-First Design (No Fallback Required)

**Decision**: Make Rust a hard requirement, like existing dependencies (`rapidfuzz`, `orjson`, `ahocorasick-rs`).

**Rationale**:
- **Rigour already requires 3 Rust-based packages** - users can already handle Rust wheels
- **Excellent PyPI coverage** - maturin supports all major platforms (>99% of users)
- **Simpler codebase** - no duplicate Python/Rust implementations to maintain
- **No performance bifurcation** - all users get optimal performance
- **Easier testing** - single implementation to validate

**Platform Support**: Pre-built wheels for Linux (x86_64, ARM64), macOS (x86_64, ARM64), Windows (x86_64). Source builds available for exotic platforms (requires Rust toolchain).

```
rigour/
├── rigour/              # Python package (existing)
│   ├── __init__.py
│   ├── addresses/
│   │   ├── __init__.py
│   │   ├── normalize.py      # Direct import from _core (no fallback)
│   │   └── ...
│   ├── names/
│   ├── text/
│   └── ...
├── rigour-core/         # Rust crate (NEW)
│   ├── Cargo.toml
│   ├── src/
│   │   ├── lib.rs           # PyO3 bindings
│   │   ├── addresses/
│   │   │   ├── mod.rs
│   │   │   └── normalize.rs
│   │   ├── names/
│   │   │   ├── mod.rs
│   │   │   └── tokenize.rs
│   │   ├── text/
│   │   │   ├── mod.rs
│   │   │   └── distance.rs
│   │   └── common/
│   │       ├── mod.rs
│   │       └── unicode.rs
│   └── benches/            # Criterion benchmarks
│       └── normalization.rs
├── pyproject.toml       # Updated with maturin build-backend
├── Makefile            # Updated with Rust targets
└── tests/              # Python tests (unchanged)
```

### Direct Import Pattern

Python modules import directly from Rust (no try/except, no fallback complexity):

```python
# rigour/addresses/normalize.py
from rigour._core import normalize_address as _normalize_address_core

def normalize_address(address: str, latinize: bool = False, min_length: int = 4) -> Optional[str]:
    """Normalize the given address string for comparison.

    This function is implemented in Rust for performance.
    """
    return _normalize_address_core(address, latinize, min_length)
```

## Repository Structure

### New Files and Directories

#### rigour-core/ (Rust Crate)

```
rigour-core/
├── Cargo.toml                  # Rust package manifest
├── Cargo.lock                 # Locked dependencies
├── build.rs                   # Build script (if needed for codegen)
├── README.md                  # Rust-specific documentation
├── src/
│   ├── lib.rs                 # Main library + PyO3 bindings
│   ├── addresses/
│   │   ├── mod.rs
│   │   ├── normalize.rs       # normalize_address implementation
│   │   ├── keywords.rs        # Address keyword replacements
│   │   └── data.rs            # Embedded address data
│   ├── names/
│   │   ├── mod.rs
│   │   ├── tokenize.rs        # tokenize_name, prenormalize_name
│   │   ├── prefix.rs          # Prefix removal
│   │   └── org_types.rs       # Organization type normalization
│   ├── text/
│   │   ├── mod.rs
│   │   ├── distance.rs        # Levenshtein, Jaro-Winkler
│   │   └── phonetics.rs       # Metaphone, Soundex
│   ├── common/
│   │   ├── mod.rs
│   │   ├── unicode.rs         # Unicode category handling
│   │   ├── cache.rs           # Rust-side caching (if needed)
│   │   └── types.rs           # Common types
│   └── data/
│       ├── mod.rs
│       └── embedded.rs        # embed! macros for data
├── benches/
│   ├── addresses.rs           # Address normalization benchmarks
│   ├── names.rs               # Name tokenization benchmarks
│   └── text.rs                # Text distance benchmarks
└── tests/
    ├── addresses.rs           # Rust unit tests
    ├── names.rs
    └── integration.rs
```

#### Cargo.toml

```toml
[package]
name = "rigour-core"
version = "1.6.2"
edition = "2021"
rust-version = "1.70"
authors = ["OpenSanctions <info@opensanctions.org>"]
license = "MIT"
description = "Performance-critical core for rigour library"
repository = "https://github.com/opensanctions/rigour"

[lib]
name = "rigour_core"
crate-type = ["cdylib", "rlib"]

[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
unicode-normalization = "0.1"
unicode-segmentation = "1.11"
ahash = "0.8"
once_cell = "1.19"
rapidfuzz = "0.5"

[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }
proptest = "1.4"

[[bench]]
name = "normalization"
harness = false

[profile.release]
lto = true
codegen-units = 1
opt-level = 3
strip = true

[profile.bench]
inherits = "release"
```

### Modified Files

#### pyproject.toml

```toml
[build-system]
requires = ["maturin>=1.5,<2.0"]
build-backend = "maturin"

[project]
name = "rigour"
version = "1.6.2"
# ... existing metadata ...

[tool.maturin]
python-source = "."
module-name = "rigour._core"
features = ["pyo3/extension-module"]
strip = true
```

#### Makefile

```makefile
# Existing targets...

# Rust targets
.PHONY: rust-dev rust-release rust-test rust-bench rust-clean

rust-dev:
	cd rigour-core && cargo build

rust-release:
	cd rigour-core && cargo build --release

rust-test:
	cd rigour-core && cargo test

rust-bench:
	cd rigour-core && cargo bench

rust-clean:
	cd rigour-core && cargo clean

# Combined build
build: build-iso639 build-territories build-addresses build-names build-text rust-release

# Python package build with Rust
package:
	maturin build --release

package-dev:
	maturin develop

# Development workflow
dev: package-dev

# Testing with Rust
test: rust-test
	pytest --cov rigour --cov-report term-missing --cov-report html tests
```

## Migration Priority: Performance-Critical Functions

### Phase 0: Normality Integration (Week 0-1)

**Goal**: Inline critical `normality` functions to avoid Python boundary crossing

**Rationale**: Rigour heavily depends on `normality` for text processing. To achieve true performance gains, we need to implement these functions in Rust rather than calling back to Python.

1. **Setup ICU Dependencies** (Priority: CRITICAL)
   - Add `rust_icu_utrans` and `rust_icu_ustring` to Cargo.toml
   - Use same ICU engine as Python's `normality` for consistent behavior
   - Document ICU system requirements (already needed for PyICU)

2. **Create Normality Module** (Priority: HIGH)
   - `normality/transliteration.rs`: `ascii_text()`, `latinize_text()`
   - `normality/cleaning.rs`: `squash_spaces()`, `remove_unsafe_chars()`
   - `normality/constants.rs`: Constants like `WS`

3. **Implementation Details**:
   - Use ICU transliterator with exact Python script: `"Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Accents-Any; [:Symbol:] Remove; [:Nonspacing Mark:] Remove; Latin-ASCII"`
   - Fast-path optimization: check if already ASCII/Latin before transliterating
   - Comprehensive tests matching Python normality behavior

**See**: [NORMALITY_INTEGRATION.md](NORMALITY_INTEGRATION.md) for detailed strategy

### Phase 1: Foundation (Week 1-2)

**Goal**: Set up infrastructure and migrate first function (`normalize_address`)

1. **Setup** (Priority: CRITICAL)
   - ✅ Create `rigour-core/` directory structure
   - ✅ Initialize Cargo workspace
   - ✅ Configure PyO3 + maturin in `pyproject.toml`
   - Update CI/CD for Rust builds
   - Add Rust toolchain to development dependencies

2. **Core Utilities** (Priority: HIGH)
   - ✅ `common/unicode.rs`: Unicode category handling
   - ✅ `common/types.rs`: Common type definitions
   - Data embedding utilities

3. **First Migration: Address Normalization** (Priority: HIGH)
   - ✅ `addresses/normalize.rs`: Port `normalize_address()` core logic
   - ⚠️ Latinization: Need to integrate `normality/transliteration.rs`
   - `addresses/keywords.rs`: Port `Replacer` class for keyword replacement
   - `addresses/data.rs`: Embed address forms data
   - ✅ Python wrapper in `rigour/addresses/normalize.py` (direct import from `_core`)
   - ⚠️ Tests: 29/30 passing (96.7%), need latinization fix

**Success Criteria**:
- `normalize_address()` passes all existing Python tests (100%)
- 5x+ performance improvement on benchmarks
- All platforms receive pre-built wheels via CI

### Phase 2: Name Processing (Week 3-4)

**Goal**: Migrate name tokenization and normalization (hot path for matching)

1. **Name Tokenization** (Priority: HIGH)
   - `names/tokenize.rs`: Port `tokenize_name()`, `prenormalize_name()`, `normalize_name()`
   - Handle Unicode category-based tokenization
   - Match Python behavior exactly (including edge cases)

2. **Prefix Removal** (Priority: MEDIUM)
   - `names/prefix.rs`: Port `remove_person_prefixes()`, `remove_org_prefixes()`
   - Load stopwords/prefix data efficiently

3. **Organization Types** (Priority: MEDIUM)
   - `names/org_types.rs`: Port org type normalization functions
   - Implement display/compare/generic normalization modes

**Success Criteria**:
- Name tokenization 8-10x faster than Python
- Memory usage reduced for batch processing
- Zero test failures

### Phase 3: String Distance (Week 5-6)

**Goal**: Optimize string comparison operations (critical for matching)

1. **Distance Metrics** (Priority: HIGH)
   - `text/distance.rs`: Port Levenshtein, Damerau-Levenshtein, Jaro-Winkler
   - Use existing Rust `rapidfuzz` crate
   - Implement similarity and plausibility checks
   - Smart caching strategy

2. **Phonetic Encoding** (Priority: MEDIUM)
   - `text/phonetics.rs`: Port Metaphone and Soundex
   - Benchmark against Python `jellyfish`

**Success Criteria**:
- Distance calculations 10x+ faster
- Matching throughput increased significantly
- Cache hit rates optimized

### Phase 4: Advanced Name Processing (Week 7-8)

**Goal**: Complete name processing pipeline

1. **Name Part Tagging** (Priority: MEDIUM)
   - `names/tagging.rs`: Port person/org name tagging
   - Efficient symbol/span management

2. **Name Alignment** (Priority: LOW)
   - `names/alignment.rs`: Port name order alignment

3. **Name Matching Utilities** (Priority: MEDIUM)
   - `names/check.rs`: Port name validation
   - `names/pick.rs`: Port name selection heuristics

### Phase 5: Optional/Future (Week 9+)

**Goal**: Additional performance improvements as needed

1. **Dictionary Operations** (Priority: LOW)
   - `text/dictionary.rs`: Port `Scanner` and `Replacer` classes
   - Use Aho-Corasick for multi-pattern matching (already have `ahocorasick-rs`)

2. **Territory Lookups** (Priority: LOW)
   - `territories/lookup.rs`: Fast territory code lookups
   - Embed territory data efficiently

3. **MIME Type Parsing** (Priority: LOW)
   - `mime/parse.rs`: Fast MIME type normalization

## Technical Decisions

### PyO3 vs. Other Binding Frameworks

**Choice**: PyO3 with maturin

**Rationale**:
- Industry standard for Rust-Python integration
- Excellent performance and safety
- `maturin` provides seamless build integration
- Active development and community support
- Used successfully by `pydantic`, `polars`, `ruff`

### Data Handling Strategy

**Approach**: Embed compiled data in Rust binary using `include_bytes!`

**Benefits**:
- No runtime data loading overhead
- Single binary distribution
- Data is validated at compile time

**Implementation**:
```rust
// src/data/embedded.rs
pub static ADDRESS_FORMS: &[u8] = include_bytes!("../../resources/addresses/forms.yml");

// Parse at initialization using once_cell
use once_cell::sync::Lazy;

static FORMS_MAP: Lazy<HashMap<String, Vec<String>>> = Lazy::new(|| {
    // Parse ADDRESS_FORMS into map
});
```

### Caching Strategy

**Approach**: Minimize caching in Rust, rely on Python's `@cache`/`@lru_cache`

**Rationale**:
- Python manages object lifecycle and memory
- Simpler to reason about memory usage
- Python's caching is already effective
- For hot paths, raw Rust speed is sufficient

**Exception**: Internal Rust caches for expensive one-time operations (data parsing)

### Unicode Handling

**Libraries**:
- `unicode-normalization`: NFC/NFD normalization
- `unicode-segmentation`: Grapheme cluster handling
- Built-in Rust `char::category()` for Unicode categories

**Strategy**: Match Python's `unicodedata` behavior exactly for compatibility

### String Distance

**Library**: `rapidfuzz` Rust crate (same as Python dependency)

**Benefits**:
- Same algorithms as Python rapidfuzz
- Excellent performance
- Well-tested

### Build Process

**Development**:
```bash
# Install maturin
pip install maturin

# Build and install in development mode
maturin develop

# Or build wheel
maturin build --release
```

**CI/CD** (GitHub Actions):
```yaml
- uses: actions/setup-python@v4
- uses: dtolnay/rust-toolchain@stable
- run: pip install maturin
- run: maturin build --release --sdist
- run: pip install target/wheels/*.whl
- run: pytest
```

## Testing Strategy

### Unit Tests

1. **Rust Tests** (`rigour-core/tests/`):
   - Test Rust functions independently
   - Property-based testing with `proptest`
   - Edge case coverage (Unicode, empty strings, very long strings)
   - Exact behavior matching with reference Python implementation

2. **Python Tests** (existing `tests/`):
   - Continue running all existing tests unchanged
   - Tests now call Rust implementations through Python API
   - Add performance regression tests to CI
   - No changes needed to test files during migration

### Integration Tests

```python
# tests/test_addresses.py (existing tests work unchanged)
def test_normalize_address():
    from rigour.addresses import normalize_address
    assert normalize_address("123 Main St") == "123 main st"
    assert normalize_address("Apt 5B, Main Street") == "apt 5b main street"

# tests/test_performance.py (new)
import time
from rigour.addresses import normalize_address

def test_normalize_address_performance():
    """Ensure Rust implementation maintains performance targets."""
    addresses = ["123 Main Street" * 10 for _ in range(1000)]

    start = time.perf_counter()
    for addr in addresses:
        normalize_address(addr)
    elapsed = time.perf_counter() - start

    # Should complete 1000 normalizations in < 5ms (5x faster than Python)
    assert elapsed < 0.005, f"Performance regression: took {elapsed}s"
```

### Migration Validation

During migration, use temporary Python reference implementation for validation:

```rust
// rigour-core/tests/addresses.rs
#[test]
fn test_normalize_matches_python() {
    // Test cases extracted from Python implementation
    let cases = vec![
        ("123 Main St", Some("123 main st")),
        ("Апартамент 5Б", Some("апартамент 5б")),
        ("", None),
        ("abc", None), // Below min_length=4
    ];

    for (input, expected) in cases {
        let result = normalize_address(input, false, 4);
        assert_eq!(result, expected.map(String::from),
            "Failed for input: {:?}", input);
    }
}
```

### Benchmarking

Use Criterion.rs for Rust benchmarks:

```rust
// benches/addresses.rs
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use rigour_core::addresses::normalize_address;

fn bench_normalize(c: &mut Criterion) {
    c.bench_function("normalize_address short", |b| {
        b.iter(|| normalize_address(black_box("123 Main St"), false, 4))
    });

    c.bench_function("normalize_address long", |b| {
        b.iter(|| normalize_address(
            black_box("Apartment 5B, 123 Main Street, Brooklyn, NY 11201"),
            false,
            4
        ))
    });
}

criterion_group!(benches, bench_normalize);
criterion_main!(benches);
```

Run with: `cargo bench`

### Performance Targets

| Function | Current (Python) | Target (Rust) | Priority |
|----------|------------------|---------------|----------|
| `normalize_address()` | 10μs | <2μs (5x) | HIGH |
| `tokenize_name()` | 8μs | <1μs (8x) | HIGH |
| `levenshtein()` | 5μs | <0.5μs (10x) | HIGH |
| `jaro_winkler()` | 4μs | <0.5μs (8x) | HIGH |
| `remove_org_prefixes()` | 15μs | <3μs (5x) | MEDIUM |

## Development Workflow

### Initial Setup

```bash
# Install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install maturin
pip install maturin

# Create Rust crate
cargo new --lib rigour-core
cd rigour-core
cargo add pyo3 --features extension-module
```

### Daily Development

```bash
# Build Rust and install in development mode
maturin develop

# Run Python tests (now using Rust implementation)
pytest

# Run Rust tests
cd rigour-core && cargo test

# Benchmark
cd rigour-core && cargo bench
```

### Release Process

```bash
# Build data files
make build

# Build Rust release
cd rigour-core && cargo build --release

# Build Python wheel with Rust
maturin build --release

# Publish to PyPI (maturin handles multi-platform builds)
maturin publish
```

## Risk Mitigation

### Risk 1: Unicode Behavior Differences

**Mitigation**:
- Extensive test coverage with Unicode edge cases
- Reference Python implementation for validation during migration
- Property-based testing to find discrepancies
- Keep Python implementation in git history for reference

### Risk 2: Performance Regression

**Mitigation**:
- Continuous benchmarking in CI
- Performance tests that fail on regression
- Profiling before/after each migration

### Risk 3: Build Complexity / Installation Issues

**Risk**: Users on exotic platforms can't install pre-built wheels

**Mitigation**:
- Pre-built wheels for 99%+ of users (all major platforms)
- Source distribution (sdist) available for source builds
- Clear documentation for building from source (requires Rust)
- Note: Users already successfully install `rapidfuzz`, `orjson`, `ahocorasick-rs` (all Rust-based)

**For source builds**:
```bash
# Automatic if Rust installed
pip install rigour

# Documentation in README:
# 1. Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# 2. pip install rigour
```

### Risk 4: Memory Safety with Python Objects

**Mitigation**:
- Use PyO3's safe abstractions
- Minimize sharing of mutable state
- Copy data across boundary when needed

### Risk 5: Breaking Changes

**Mitigation**:
- 100% API compatibility requirement
- All existing tests must pass
- Semantic versioning (breaking changes = major version bump)

## Platform Support

### Primary Platforms (Tier 1)

- Linux x86_64 (manylinux)
- macOS x86_64
- macOS ARM64 (Apple Silicon)
- Windows x86_64

### Secondary Platforms (Tier 2)

- Linux ARM64
- Linux i686

### Build Matrix

Use `maturin` with GitHub Actions for cross-platform wheels:

```yaml
strategy:
  matrix:
    platform:
      - os: ubuntu-latest
        target: x86_64
      - os: macos-latest
        target: x86_64
      - os: macos-latest
        target: aarch64
      - os: windows-latest
        target: x86_64
```

## Success Metrics

### Performance Goals

- **5-10x speedup** on hot-path functions
- **30% reduction** in memory usage for batch processing
- **Zero performance regression** on any existing function

### Quality Goals

- **100% test coverage** for migrated functions
- **Zero API breaking changes**
- **< 5% increase** in package size

### Adoption Goals

- **Seamless installation** on all platforms
- **< 1 day** for contributors to set up Rust development
- **Positive community feedback** on performance

## Documentation Requirements

### For Users

- Update [README.md](README.md) with Rust information
- Installation instructions with/without Rust
- Performance comparisons
- Troubleshooting guide

### For Contributors

- Rust development setup guide
- Architecture documentation
- Porting guidelines (this document)
- Benchmarking procedures

### For Maintainers

- Release process with Rust
- CI/CD configuration
- Platform support matrix

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|-------------|
| Phase 1: Foundation | 2 weeks | Setup + `normalize_address()` |
| Phase 2: Name Processing | 2 weeks | Tokenization + prefix removal |
| Phase 3: String Distance | 2 weeks | Distance metrics + phonetics |
| Phase 4: Advanced Names | 2 weeks | Tagging + alignment |
| Phase 5: Polish | 2+ weeks | Documentation + optimization |

**Total**: ~10 weeks for core migration

## Starting Point: normalize_address

### Implementation Plan

1. **Create Rust module** (`rigour-core/src/addresses/normalize.rs`)
2. **Port core logic**:
   - Unicode category handling
   - Token extraction
   - Latinization (via transliteration)
   - Minimum length filtering
3. **PyO3 bindings** in `src/lib.rs`
4. **Python wrapper** in `rigour/addresses/normalize.py` (direct import from `_core`)
5. **Tests**:
   - Port all existing Python test cases to Rust
   - Ensure Python tests pass with Rust implementation
   - Add property-based tests for edge cases
6. **Benchmark**: Validate 5x+ performance improvement over Python
7. **CI**: Configure maturin to build wheels for all platforms

### Expected Code Structure

```rust
// rigour-core/src/addresses/normalize.rs
use unicode_normalization::UnicodeNormalization;

pub fn normalize_address(
    address: &str,
    latinize: bool,
    min_length: usize,
) -> Option<String> {
    let mut tokens: Vec<String> = Vec::new();
    let mut current_token = String::new();

    for ch in address.to_lowercase().chars() {
        if is_allowed_char(ch) {
            current_token.push(ch);
        } else {
            let cat = unicode_category(ch);
            match cat {
                UnicodeCategory::Separator => {
                    if !current_token.is_empty() {
                        tokens.push(current_token.clone());
                        current_token.clear();
                    }
                }
                UnicodeCategory::Skip => continue,
                _ => current_token.push(ch),
            }
        }
    }

    if !current_token.is_empty() {
        tokens.push(current_token);
    }

    let result = tokens.join(" ");
    if result.len() >= min_length {
        Some(result)
    } else {
        None
    }
}
```

```python
# rigour/addresses/normalize.py
from rigour._core import normalize_address as _normalize_address_core

def normalize_address(
    address: str, latinize: bool = False, min_length: int = 4
) -> Optional[str]:
    """Normalize the given address string for comparison.

    Implemented in Rust for performance.
    """
    return _normalize_address_core(address, latinize, min_length)

# Note: Original Python implementation removed after migration.
# See git history (commit XXXXX) for reference implementation.
```

## Next Steps

1. **Review and approve** this plan
2. **Set up development environment** with Rust + maturin
3. **Create initial repository structure** for `rigour-core/`
4. **Implement Phase 1**: Foundation + `normalize_address()`
5. **Benchmark and validate** before proceeding to Phase 2

## Resources

- [PyO3 Guide](https://pyo3.rs/)
- [Maturin Documentation](https://www.maturin.rs/)
- [Rust Performance Book](https://nnethercote.github.io/perf-book/)
- [unicode-rs libraries](https://github.com/unicode-rs)
- [RapidFuzz Rust](https://docs.rs/rapidfuzz/)

---

**Document Version**: 1.0
**Last Updated**: 2026-01-31
**Author**: OpenSanctions Development Team
