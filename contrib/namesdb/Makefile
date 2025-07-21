

# TODO: upload with timestamp

put:
	sqlite3 data/names.db 'DELETE FROM cache WHERE timestamp < datetime("now", "-90 days");'
	sqlite3 data/names.db 'VACUUM;'
	gsutil cp data/names.db gs://internal-data.opensanctions.org/namesdb/names.db
	gsutil cp gs://internal-data.opensanctions.org/namesdb/names.db gs://internal-data.opensanctions.org/namesdb/names.$(shell date +%Y-%m-%d).db

get:
	gsutil cp gs://internal-data.opensanctions.org/namesdb/names.db data/names.db 

wikidata:
	python namesdb/wikidata.py

dump:
	ndb dump ../../rigour/data/names/persons.txt