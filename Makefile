typecheck:
	mypy --strict rigour

test:
	pytest --cov rigour --cov-report term-missing tests