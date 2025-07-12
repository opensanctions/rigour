

# TODO: upload with timestamp

put:
	gsutil cp data/names.db gs://internal-data.opensanctions.org/namesdb/names.db
	gsutil cp data/names.db gs://internal-data.opensanctions.org/namesdb/names.$(shell date +%Y-%m-%d).db

get:
	gsutil cp gs://internal-data.opensanctions.org/namesdb/names.db data/names.db 

dump:
	ndb dump ../../rigour/data/names/persons.txt