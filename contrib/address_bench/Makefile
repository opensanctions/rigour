STATEMENTS ?= $(HOME)/Data/statements-apr26.csv

candidates:
	python generate.py --statements $(STATEMENTS)

sample:
	python adjudicate.py --limit 50

adjudicate:
	python adjudicate.py

stats:
	qsv frequency -s case_group,is_match,quality cases.csv | qsv table
	qsv frequency -s category --limit 30 cases.csv | qsv table

typecheck:
	mypy --strict generate.py adjudicate.py
