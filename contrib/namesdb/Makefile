

# TODO: upload with timestamp

put:
	sqlite3 data/names.db '.dump' | gzip > data/names.sql.gz
	gsutil cp data/names.sql.gz gs://internal-data.opensanctions.org/namesdb/names.sql.gz
	gsutil cp gs://internal-data.opensanctions.org/namesdb/names.sql.gz gs://internal-data.opensanctions.org/namesdb/names.$(shell date +%Y-%m-%d).sql.gz

get:
	gsutil cp gs://internal-data.opensanctions.org/namesdb/names.sql.gz data/names.sql.gz 

wikidata:
	python namesdb/wikidata.py

dump:
	ndb dump ../../rigour/data/names/persons.txt