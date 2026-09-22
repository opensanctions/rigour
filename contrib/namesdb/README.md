# Name mapping database project

This is a nascent effort to provide a QA layer for name mappings that are eventually going to be used by rigour.

## Language metadata and training CSV

Besides the `mapping` table (one row per `form` and `group`, with the
`skip` QA flag), the crawl stores one row per Wikidata item in `item`:

* `classes` — space-joined P31 QIDs among the crawled name classes
  (family name, male given name, patronymic, …).
* `names` — JSON `{form: {lang: source}}` with the *raw* Wikidata language
  codes (`en`, `sv`, `mul`, `sr-el`, …) a form appears under. `source` is a
  bitmask: label `1`, alias `2`, P1705 native label `4`, P2440
  transliteration `8`. P2440 values are plain strings; their language comes
  from the P424 qualifier, else from same-spelled labels on the item, else
  `und`.
* `schemes` — JSON `{form: QID}` of the P459 (determination method)
  qualifier on P2440 claims, i.e. the transliteration standard.

`ndb export-csv PATH` writes one row per item and form for a training
process (column semantics in [NAME_FORMS.md](NAME_FORMS.md)): `group, classes, native_langs, form, script, langs, source,
scheme`, where `langs` is the space-joined code list, `script` the single
Unicode script of the form (empty when mixed), `source` the letters
`L A N T` for the bits above and `native_langs` the item's P1705
language(s). Skipped forms and blocklisted groups are left out.

To fill `item` for a database crawled before it existed:

```bash
ndb backfill     # re-parse cached Wikidata responses, no new requests
ndb export-csv data/name_forms.csv
```

Items missing from the cache pick up their row on the next crawl.

## Cleanup

```sql
UPDATE mapping SET skip = true WHERE form LIKE '%family name%';
UPDATE mapping SET skip = true WHERE form LIKE '%surname%';
UPDATE mapping SET skip = true WHERE form LIKE '%given name%';
UPDATE mapping SET skip = true WHERE form LIKE '%male name%';
UPDATE mapping SET skip = true WHERE form LIKE '%son of%';
UPDATE mapping SET skip = true WHERE form LIKE '%head of%';
UPDATE mapping SET skip = true WHERE form LIKE '%adelsgeschlecht%';
UPDATE mapping SET skip = true WHERE form LIKE '%cap de la casa%';
```

SELECT form, COUNT(*) FROM mapping GROUP BY form ORDER BY COUNT(*) DESC LIMIT 50;