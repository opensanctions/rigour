.PHONY: docs build typecheck test develop develop-debug rust-test rust-fmt rust-fmt-check bench build-iso639 build-territories build-addresses build-names build-text

check: build typecheck test

# Release build by default: the ICU4X trie-heavy transliteration path is
# ~100x slower in debug and benchmark numbers are meaningless there. Use
# `make develop-debug` for fast Rust-iteration cycles where speed of the
# compiled code doesn't matter.
develop:
	maturin develop --manifest-path rust/Cargo.toml --release

develop-debug:
	maturin develop --manifest-path rust/Cargo.toml

rust-test:
	cargo test --manifest-path rust/Cargo.toml

# Format Rust sources in place. CI runs `cargo fmt --check` so drift
# fails the build; this target is the one-command local fix. Run it
# before committing Rust changes.
rust-fmt:
	cargo fmt --manifest-path rust/Cargo.toml

rust-fmt-check:
	cargo fmt --manifest-path rust/Cargo.toml --check

bench:
	python benchmarks/bench_transliteration.py

typecheck:
	mypy --strict rigour

test:
	pytest --cov rigour --cov-report term-missing --cov-report html tests

fetch-scripts:
	curl -o resources/text/scripts.txt https://www.unicode.org/Public/UCD/latest/ucd/Scripts.txt

fetch: fetch-scripts

build-iso639:
	python genscripts/generate_langs.py

build-territories:
	python genscripts/generate_territories.py

build-addresses:
	python genscripts/generate_addresses.py

build-names:
	python genscripts/generate_names.py

build-text:
	python genscripts/generate_text.py

# Regenerate every data artifact in the repo, both Rust-consumed
# (under rust/data and rust/src/generated, from the names / text /
# territories / addresses generators) and Python-consumed (the
# iso639 and addresses tables that haven't been ported to Rust yet).
# Generators are dual-emit, so running build keeps Rust + Python
# tables in lockstep. CI calls this + git-diffs rust/data and
# rust/src/generated to catch stale checkins.
build: build-iso639 build-territories build-addresses build-names build-text

docs:
	mkdocs build -c -d site