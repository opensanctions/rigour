.PHONY: docs build typecheck test develop develop-debug rust-test bench rust-data build-iso639 build-territories build-addresses build-names

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

build: build-iso639 build-territories build-addresses build-names build-text

# Regenerate Rust-consumed data artifacts (under rust/data and
# rust/src/generated). Generators are dual-emit — running them produces the
# Rust artifacts alongside the existing Python ones, which keeps the two
# from drifting. CI calls this + git-diffs to catch stale checkins.
rust-data: build-names

docs:
	mkdocs build -c -d site