# rigour

Data cleaning and validation functions for processing various types of text emanating and describing the business world. This applies to human and company names, language, territory
and country codes, corporate and tax identifiers, etc.

The underlying idea is that handling these sorts of descriptors is easy on first glance, but reveals a dizzying set of complexity when carried into production. This is why `rigour` consolidates implementations that have already met some edge cases and are well-tested.

## Installing `rigour`

You can grab the latest release from PyPI:

```bash
pip install -U rigour
```

## Usage & documentation

See: https://rigour.followthemoney.tech/

## Development

`rigour` uses a mixed Python/Rust architecture for performance-critical operations. Performance-sensitive functions (address normalization, name tokenization, text transliteration) are implemented in Rust and exposed to Python via PyO3.

### Requirements

- Python 3.10+
- Rust toolchain (stable)
- ICU library (International Components for Unicode)
- pkg-config

### Building from source

#### macOS (Homebrew)

```bash
# Install ICU
brew install icu4c pkg-config

# Set environment variables for ICU
export PKG_CONFIG_PATH="/opt/homebrew/opt/icu4c@78/lib/pkgconfig:$PKG_CONFIG_PATH"
export ICU_ROOT="/opt/homebrew/opt/icu4c@78"

# Install in development mode
pip install -U pip maturin
pip install -e ".[dev]"
```

#### Linux (Ubuntu/Debian)

```bash
# Install ICU and build tools
sudo apt-get install libicu-dev pkg-config

# Install in development mode
pip install -U pip maturin
pip install -e ".[dev]"
```

### Running tests

```bash
make test
```

### Project structure

- `rigour/` - Python API and high-level logic
- `rigour-core/` - Rust implementation of performance-critical functions
- `tests/` - Test suite

See [RUST_STATUS.md](RUST_STATUS.md) for details on the Rust migration.

## Acknowledgements

The address formatting database contained in `rigour/data/addresses/formats.yml` is derived from `worldwide.yml` in the [OpenCageData address-formatting repository](https://github.com/OpenCageData/address-formatting). It is used to format addresses according to customs in the country that is been encoded.

`rigour` consolidates and includes a set of older Python libraries into a single codebase: `languagecodes`, `pantomime`, `fingerprints`. The development of these libraries was funded by OCCRP as part of the Aleph software project.

## License

MIT. See `LICENSE`.