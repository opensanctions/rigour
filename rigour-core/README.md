# rigour-core

Performance-critical Rust implementation for the `rigour` Python library.

This crate provides high-performance implementations of data normalization and validation functions using PyO3 for Python bindings.

## Building

```bash
# Development build
cargo build

# Release build
cargo build --release

# Run tests
cargo test

# Run benchmarks
cargo bench
```

## For Python Integration

This crate is built and distributed as part of the `rigour` Python package using `maturin`. See the main README for installation instructions.
