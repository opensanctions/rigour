typecheck:
	mypy --strict rigour

test:
	pytest --cov rigour --cov-report term-missing tests

build-iso639:
	python rigour/langs/generate.py

build: build-iso639
	black rigour/data
