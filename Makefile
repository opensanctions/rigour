.PHONY: docs build typecheck test build-iso639 build-territories build-addresses build-names

check: build typecheck test

typecheck:
	mypy --strict rigour

test:
	pytest --cov rigour --cov-report term-missing tests

fetch-scripts:
	curl -o resources/text/scripts.txt https://www.unicode.org/Public/UCD/latest/ucd/Scripts.txt

fetch-opencage-addresses:
	curl -o resources/addresses/opencage_worldwide.yaml https://raw.githubusercontent.com/OpenCageData/address-formatting/refs/heads/master/conf/countries/worldwide.yaml

fetch: fetch-scripts fetch-opencage-addresses

build-iso639:
	python genscripts/generate_langs.py

build-territories:
	python genscripts/generate_territories.py

build-addresses:
	python genscripts/generate_addresses.py

build-names:
	python genscripts/generate_names.py

build-address-formats:
	python genscripts/generate_address_formats.py

build: build-iso639 build-territories build-addresses build-names build-address-formats

docs:
	mkdocs build -c -d site