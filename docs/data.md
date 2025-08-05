# Core reference data

Investigating financial crime requires contextual data about multiple aspects of the real world. This includes human names, political geography, and other areas. By producing such data assets as open source reference data, we hope to make a positive contribution to the state of the art in screening and investigative technology.

## Person and company names

For name matching, we produce four classes of data assets:

* **Stopwords** ([YAML](https://github.com/opensanctions/rigour/blob/main/resources/names/stopwords.yml)) are name parts that can be fully removed from a name prior to name comparison. Stopwords include words that appear with high frequency in normal language that are considered to be of very limited use in disambiguating entities. Examples of stopwords include the English words "the", "of" and "from" and their equivalents in other languages.
    - The stopwords data includes prefixes (like `Mr`, `Mrs.`, `President`) that can be removed from the beginning of person, organisation or other names.
* **Organisation type labels** ([YAML](https://github.com/opensanctions/rigour/blob/main/resources/names/org_types.yml)) are extensively mapped from real-world data, to allow three different normalisation forms: 
    - *Display normalisation* is intended for user-facing re-writes of organisation types. It offers a cosmetic simplification for name cleaning. Example: `Aktiengesellschaft` becomes `AG`, `ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ` becomes `ООО`. 
    - *Compare normalisation* is designed to facilitate string-based comparison of company types, e.g. `Sp. z o.o.` becomes `spzoo`, `G.m.beschr. Haftung` becomes `gmbh`. 
    - *Generic normalisation* attempts a basic global alignment of organisation types. `Aktiengesellschaft` becomes `JSC`, `ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ` and  `Sp. z o.o.` become `LLC`.
* **Organisation symbols** ([YAML](https://github.com/opensanctions/rigour/blob/main/resources/names/symbols.yml)) are mappings of common terms and phrases found in company names (like `Holding`, `Group`, `Company`, or `Technology`) across various spelling variants and languages (eg. `Holding`, `холдинг`, `集体`). Symbols do not imply a canonical form. Instead, they can be used as reciprocal synonyms and matched (and then eliminated) before string comparison is applied. This helps to avoid match biases introduced by long, but ultimately meaningless, name parts. Numbers in both their cardinal forms and ordinal forms are treated as a special type of symbol (eg. `12th`, `Nr. 12`, `№ 12`, XII). They can often be used to disambiguate two entities.
* **Person names** ([TXT](https://github.com/opensanctions/rigour/blob/main/rigour/data/names/persons.txt)) is a database of hundreds of thousands of human name part mappings. Again, the idea is not to provide canonicalisation, but to be able to identify synonyms inside of a matching process (eg. `salman`, `салман`, `салмон`, `סלמאן`, `सलमान`, `サルマーン`, `살만`). This allows for name matching across scripts without the need to rely on machine-based transliteration. 

## Territories

The [database of territories](https://github.com/opensanctions/rigour/tree/main/resources/territories) includes countries, sub-country jurisdictions (think: `Delaware`, `Dubai`), some historical jurisdictions (eg: `Yugoslavia`, `USSR`) and disputed territories (eg: `Transnistria`, `Crimea`, `Somaliland`). Metadata for each jurisidiction includes:

* Territory names in short and long form, name of region and subregion.
* Corresponding [Wikidata QID](https://www.wikidata.org/wiki/Wikidata:Identifiers), and alternate Wikidata QIDs for similar items.
* Relationship to other territories (parent/child, successor/predecessor, see also).
* ISO 3166-2 codes where applicable, including previous codes and custom country codes for unrecognized territories.
* Tags on whether a territory is considered an *independent country* or a *legal jurisdiction*.

## Addresses

This library does not perform geocoding and treats address matching as a text comparison, and not a geodesic problem. In order to allow for better string comparison between two address strings, we include an alias mapping file which re-writes common terms used in addresses to increase the chance of a string match (eg. `Street` -> `St`). 

* [forms.yml](https://github.com/opensanctions/rigour/blob/main/resources/addresses/forms.yml)

See also: 

* [libpostal](https://github.com/openvenues/libpostal) is a fully developed C library for address parsing and normalisation that is trained on OpenStreetMap data.
* [addressformatting](https://github.com/OpenCageData/address-formatting) solves the inverse problem: given a set of address components (like street, city, postal code), it will create a text representation that is in line with local expectations in the given country.
