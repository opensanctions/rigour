# `name_forms.csv` — personal-name forms with language and script metadata

A flat export of personal-name items mined from Wikidata, intended as
raw material for training transliteration models. Produced by
`ndb export-csv` from the namesdb database; regenerate with
`make backfill csv` in `contrib/namesdb/`.

Snapshot of 2026-09-22: 150,587 rows over 94,234 items, 76 MB, UTF-8,
comma-separated, header row, RFC 4180 quoting.

## What a row is

One row per **item** and **form**. An item is one Wikidata entity
describing a name (a family name, a given name, a patronymic, …). A
form is one spelling of that name, in any script, as it appears in the
item's labels, aliases, native-label claim (P1705) or transliteration
claims (P2440).

All forms of one item denote the same name. Rows sharing a `group`
therefore form an equivalence set, and cross-script pairs for training
are built by joining rows on `group` and picking rows with different
`script` values. The file itself contains no pairs and no scores.

## Columns

| column | type | meaning |
|---|---|---|
| `group` | `Q…` | Wikidata item id, e.g. `Q10000042` → https://www.wikidata.org/wiki/Q10000042 |
| `classes` | space-joined `Q…` | The item's `P31` (instance of) values that fall inside the crawled name classes, sorted. See the class table below. Empty in a handful of rows where the item reached the crawl through a class not listed. |
| `native_langs` | space-joined codes | Language tags of the item's `P1705` native-label claims. Item-level: identical on every row of a group. Empty when the item has no P1705. |
| `form` | text | The name form, cleaned (see below). |
| `script` | Unicode script name | The single Unicode script of the form (`Latin`, `Cyrillic`, `Han`, `Katakana`, `Arabic`, …). Empty when the form mixes scripts or contains no letters. |
| `langs` | space-joined codes | Every Wikidata language code the form appears under on the item, sorted. See "Language codes". |
| `source` | letters from `L A N T` | Where the form was seen on the item, OR-ed over all its languages: `L` label, `A` alias, `N` P1705 native label, `T` P2440 transliteration. |
| `scheme` | `Q…` | For forms that come from a P2440 claim: the `P459` (determination method) qualifier, i.e. the transliteration standard the form follows. Empty otherwise, or when the claim has no P459. |

### Class ids in `classes`

| QID | class |
|---|---|
| Q101352 | family name |
| Q4116295 | surname |
| Q120707496 | second family name (Spanish naming) |
| Q121493728 | first family name (Spanish naming) |
| Q66475447 | family name affix |
| Q202444 | given name |
| Q12308941 | male given name |
| Q11879590 | female given name |
| Q3409032 | unisex given name |
| Q122067883 | given name component |
| Q245025 | middle name |
| Q110874 | patronymic |
| Q130444148 | masculine patronymic |
| Q130444179 | feminine patronymic |
| Q1076664 | matronymic |
| Q130443873 | masculine matronymic |
| Q130443889 | feminine matronymic |
| Q12717622 | parentonymic |
| Q200835 | religious title of honour |

An item can carry several, e.g. `Q101352 Q110874` for a name used both
as a family name and a patronymic. In the snapshot 80% of rows are
family names and 17% female given names; male given names are rare
(129 rows) because few of them were in the response cache at export
time. The balance shifts as crawls revisit items.

### Form cleaning

Forms are what `clean_form` / `clean_wikidata_name` in namesdb leave
of the Wikidata text:

- lowercased, Unicode NFC, control and unsafe characters removed;
- bracketed text `(…)` and emoji removed, then trimmed;
- a value containing `/` is split into several forms;
- a form containing any of `, ( / = :` is dropped, as are forms longer
  than 40 characters and single-character forms in alphabetic scripts;
- a form must pass rigour's `is_name` check.

Lowercasing is lossy for case-carrying scripts. Diacritics are kept.

### Language codes

`langs` and `native_langs` carry Wikidata's own codes, not ISO 639-3.
They include:

- ordinary codes: `en`, `de`, `ru`, `ja`, …;
- script and region variants that matter for transliteration:
  `zh-hans`, `zh-hant`, `zh-tw`, `sr-el` (Serbian Latin), `sr-ec`
  (Serbian Cyrillic), `kk-latn`, `kk-cyrl`, `tg-latn`, `be-tarask`,
  `pt-br`, …;
- `mul`: Wikidata's tag for a language-independent value. Very common
  on family names, both as a label and as the P1705 language: 60% of
  rows have `native_langs = mul`, meaning Wikidata asserts the native
  spelling but not a language for it;
- `und`: used only by this export, for a P2440 transliteration whose
  language Wikidata leaves open (493 rows). See below.

**Wide lists.** Bots copy family-name labels into every Wikipedia
language, so about a third of rows carry 100–300 codes in `langs`
(`aa ab ace … zh-tw zu`). Such a list means "this spelling is used
everywhere", not "this spelling is English and also Zulu". A long list
is best read as equivalent to `mul`; the informative language tags are
the ones on forms with short lists, and on `N`/`T` forms.

### Provenance and P2440

- `L`/`A` forms come from labels and aliases; their `langs` are the
  label/alias languages.
- `N` forms come from the P1705 native-label claim, which is
  monolingual text and carries its own language.
- `T` forms come from P2440 transliteration claims, which are plain
  strings in Wikidata. Their language in `langs` is attributed as
  follows: the `P424` (Wikimedia language code) qualifier when present;
  otherwise the languages of labels or aliases on the same item that
  spell the form identically; otherwise `und`. A form that is both a
  label and a P2440 value shows as `LT`.

`scheme` is only ever set on `T` forms. In the snapshot 2,706 rows are
`T` and 2,578 of those have a scheme; the most frequent are Q2622924
(949), Q94489556 (196), Q56342653 (154), Q4835559 and Q56343745 (100
each). Resolve them on Wikidata; they are transliteration standards
such as ISO 9 or BGN/PCGN romanisations.

## What is left out

- Forms manually marked as skipped in the namesdb QA layer (`mapping.skip`),
  and forms matching the blocklists in `namesdb/blocks.py` (descriptive
  phrases like "family name", "prénom", "persone di cognome" that leak
  into labels). Items whose every form is skipped produce no rows.
- Manually created groups (`X…` ids) that have no Wikidata item.
- Items not present in the local Wikidata response cache at export
  time. The database has 772k items in its `mapping` table but only
  94k had a cached response; the rest join the CSV as crawls revisit
  them.
- Deprecated-rank claims.
- No deduplication across items: if two items share forms (e.g. a name
  that exists as both a family-name and a given-name item), both appear
  under their own `group`. `person_names.txt` deduplicates for the
  rigour tagger; this file does not.

## Provenance and licence

All values are Wikidata content (CC0). The crawl runs the SPARQL query
`?item wdt:P31 wd:<class>` for each class above and fetches each item
through the `wbgetentities` API. Cached responses are at most ~200 days
old at export time.
