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

SCORER ?= nomenklatura

evaluate:
	python evaluate.py --scorer $(SCORER)

FINGERPRINT ?= ftm

collapse:
	python collapse.py --fingerprint $(FINGERPRINT)

perf:
	python perf.py

typecheck:
	mypy --strict generate.py adjudicate.py evaluate.py collapse.py perf.py
