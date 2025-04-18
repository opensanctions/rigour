.PHONY: docs build typecheck test build-iso639 build-territories build-addresses build-names

check: build typecheck test

typecheck:
	mypy --strict rigour

test:
	pytest --cov rigour --cov-report term-missing tests

build-iso639:
	python genscripts/generate_langs.py

build-territories:
	python genscripts/generate_territories.py

build-addresses:
	python genscripts/generate_addresses.py

build-names:
	python genscripts/generate_names.py

build: build-iso639 build-territories build-addresses build-names

docs:
	mkdocs build -c -d site