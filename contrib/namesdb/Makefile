

# TODO: upload with timestamp

clean:
	sqlite3 data/names.db "DELETE FROM cache WHERE timestamp < datetime('now', '-100 days');"
	sqlite3 data/names.db 'VACUUM;'

put:
	sqlite3 data/names.db '.dump' | gzip > data/names.sql.gz
	gsutil cp data/names.sql.gz gs://internal-data.opensanctions.org/namesdb/names.sql.gz
	gsutil cp gs://internal-data.opensanctions.org/namesdb/names.sql.gz gs://internal-data.opensanctions.org/namesdb/names.$(shell date +%Y-%m-%d).sql.gz

get:
	gsutil cp gs://internal-data.opensanctions.org/namesdb/names.sql.gz data/names.sql.gz 

wikidata:
	python namesdb/wikidata.py

dump:
	ndb dump ../../rust/data/names/person_names.txt

quickstatements:
	ndb quickstatements data/quickstatements.tsv --min-shared 4 --min-jaccard 0.7 --max-per-pair 5 --limit 500