.PHONY: docs

check: build typecheck test

typecheck:
	mypy --strict rigour

test:
	pytest --cov rigour --cov-report term-missing tests

build-iso639:
	python rigour/langs/generate.py

build-territories:
	python rigour/territories/generate.py

build-addresses:
	python rigour/addresses/generate.py

build: build-iso639 build-territories build-addresses
	black rigour/data

docs:
	mkdocs build -c -d site