# Rigour Library Description

**Version**: 1.6.2
**Description**: Financial crime domain data validation and normalization library
**Documentation**: https://rigour.followthemoney.tech/
**Repository**: https://github.com/opensanctions/rigour

## Overview

`rigour` is a comprehensive Python library for data cleaning and validation of text describing the business world. It handles person and company names, languages, territories, corporate identifiers, addresses, and more. The library consolidates production-tested implementations that handle edge cases commonly encountered when processing real-world data in financial crime investigation and sanctions compliance contexts.

The library evolved from consolidating several standalone libraries (`languagecodes`, `pantomime`, `fingerprints`) into a single, cohesive codebase developed as part of the [FollowTheMoney](https://followthemoney.tech) ecosystem and funded by OCCRP for the Aleph project.

## Build System

### Build Configuration

- **Build System**: [Hatchling](https://github.com/pypa/hatch) (PEP 517 compliant)
- **Configuration File**: [pyproject.toml](pyproject.toml)
- **Python Requirements**: >= 3.10 (supports 3.10, 3.11, 3.12)
- **License**: MIT

### Build Process

The library uses a two-stage build process defined in [Makefile](Makefile):

1. **Data Generation** (`make build`): Compiles reference data from YAML sources in `resources/` into optimized formats in `rigour/data/`:
   - `make build-iso639`: Generates language code mappings from ISO 639 data
   - `make build-territories`: Compiles territory/jurisdiction database
   - `make build-addresses`: Processes address formatting templates
   - `make build-names`: Builds name processing databases (stopwords, org types, symbols, person names)
   - `make build-text`: Generates text processing resources (Unicode scripts)

2. **Package Build**: Standard Python wheel/sdist creation via `hatchling`

### Generation Scripts

Located in [genscripts/](genscripts/):
- [generate_langs.py](genscripts/generate_langs.py): ISO 639 language code processing
- [generate_territories.py](genscripts/generate_territories.py): Territory data compilation
- [generate_addresses.py](genscripts/generate_addresses.py): Address format processing
- [generate_names.py](genscripts/generate_names.py): Name database compilation
- [generate_text.py](genscripts/generate_text.py): Unicode script data generation

### Dependencies

**Core Dependencies**:
- `pyicu` (2.x): Unicode/ICU library for text processing
- `babel` (2.x): Internationalization utilities
- `pyyaml` (5.x-6.x): YAML parsing for reference data
- `banal` (1.0.x): Data validation utilities
- `normality` (3.x): Text normalization
- `jellyfish` (1.x): Phonetic encoding algorithms
- `rapidfuzz` (3.9.x): Fast string matching
- `orjson` (3.x): Fast JSON serialization
- `fingerprints` (1.x): Text fingerprinting
- `python-stdnum` (2.x): Standard number formats (identifiers)
- `jinja2` (3.x): Template rendering (for address formatting)
- `ahocorasick-rs` (0.22.x): Fast multi-pattern string matching

**Development Dependencies**: pytest, mypy, black, coverage
**Documentation Dependencies**: mkdocs, mkdocs-material, mkdocstrings

## Module Structure

The library consists of 74 Python files organized into the following submodules:

### 1. Names Module ([rigour/names/](rigour/names/))

**Purpose**: Person and organization name handling, normalization, and comparison.

**Key Files**:
- [name.py](rigour/names/name.py): `Name` class - structured representation of names with parts, tags, and metadata
- [part.py](rigour/names/part.py): `NamePart` and `Span` classes for individual name components
- [symbol.py](rigour/names/symbol.py): `Symbol` class for cross-language synonym matching
- [tag.py](rigour/names/tag.py): `NamePartTag` and `NameTypeTag` enums for classification
- [tokenize.py](rigour/names/tokenize.py): Name tokenization and normalization functions
- [person.py](rigour/names/person.py): Person name database loading and matching
- [prefix.py](rigour/names/prefix.py): Functions to remove prefixes (Mr., Dr., etc.)
- [org_types.py](rigour/names/org_types.py): Organization type normalization (Inc., Ltd., GmbH, etc.)
- [tagging.py](rigour/names/tagging.py): Name part tagging for person and organization names
- [alignment.py](rigour/names/alignment.py): Name order alignment (given/family name)
- [pick.py](rigour/names/pick.py): Functions to select best name from alternatives
- [check.py](rigour/names/check.py): Name validation functions

**Key Functions**:
- `tokenize_name()`, `prenormalize_name()`, `normalize_name()`: Text normalization pipeline
- `remove_person_prefixes()`, `remove_org_prefixes()`, `remove_obj_prefixes()`: Prefix removal
- `replace_org_types_display()`, `replace_org_types_compare()`: Organization type normalization
- `tag_person_name()`, `tag_org_name()`: Intelligent name part tagging
- `pick_name()`, `pick_case()`, `reduce_names()`: Name selection heuristics
- `load_person_names()`, `load_person_names_mapping()`: Person name database access

**Documentation**: [docs/names.md](docs/names.md)

### 2. Territories Module ([rigour/territories/](rigour/territories/))

**Purpose**: Countries, jurisdictions, and political geography handling.

**Key Files**:
- [territory.py](rigour/territories/territory.py): `Territory` class representing countries, jurisdictions, historical entities
- [lookup.py](rigour/territories/lookup.py): Territory lookup by various identifiers
- [match.py](rigour/territories/match.py): Territory matching and intersection logic
- [tagging.py](rigour/territories/tagging.py): Territory mention detection in text
- [util.py](rigour/territories/util.py): Territory code cleaning utilities

**Key Functions**:
- `get_territory()`: Get territory by ISO code
- `get_territories()`: Get all territories
- `get_territory_by_qid()`: Lookup by Wikidata QID
- `get_ftm_countries()`: Get FollowTheMoney-compatible countries
- `lookup_by_identifier()`, `lookup_territory()`: Flexible territory lookup
- `territories_intersect()`: Check if two territories overlap

**Territory Features**:
- ISO 3166-1/3166-2 codes, alpha-2 and alpha-3 formats
- Wikidata QID mappings
- Parent/child relationships (e.g., states within countries)
- Successor/predecessor relationships (historical entities)
- Regional classification (region, subregion)
- Jurisdiction indicators (legal incorporation regimes)

**Documentation**: [docs/territories.md](docs/territories.md)

### 3. Addresses Module ([rigour/addresses/](rigour/addresses/))

**Purpose**: Postal address normalization, cleaning, and formatting.

**Key Files**:
- [cleaning.py](rigour/addresses/cleaning.py): Address text cleaning
- [normalize.py](rigour/addresses/normalize.py): Address comparison normalization
- [format.py](rigour/addresses/format.py): Country-specific address formatting

**Key Functions**:
- `clean_address()`: Clean address text
- `normalize_address()`: Normalize for comparison
- `remove_address_keywords()`, `shorten_address_keywords()`: Keyword processing
- `format_address()`, `format_address_line()`: Format address parts into text

**Features**:
- Country-specific formatting templates (based on OpenCageData address-formatting)
- Address keyword normalization (Street → St, Avenue → Ave)
- Text-based comparison (not geocoding)

**Acknowledgements**: Address formats derived from OpenCageData's [address-formatting](https://github.com/OpenCageData/address-formatting) repository.

**Documentation**: [docs/addresses.md](docs/addresses.md)

### 4. Languages Module ([rigour/langs/](rigour/langs/))

**Purpose**: ISO 639 language code normalization and handling.

**Key Files**:
- [text.py](rigour/langs/text.py): `LangStr` class for language-tagged strings
- [synonyms.py](rigour/langs/synonyms.py): Language synonym expansion
- [util.py](rigour/langs/util.py): Language code utilities

**Key Functions**:
- `iso_639_alpha3()`: Convert to 3-letter ISO 639-2/3 codes (e.g., 'en' → 'eng')
- `iso_639_alpha2()`: Convert to 2-letter ISO 639-1 codes (e.g., 'eng' → 'en')
- `list_to_alpha3()`: Convert list of codes with synonym expansion
- `is_lang_better()`: Compare language preferences

**Constants**:
- `PREFERRED_LANG`: Default preferred language (default: 'eng', configurable via `RR_PREFERRED_LANG`)
- `PREFERRED_LANGS`: Ordered list of preferred languages (bias toward European languages with Latin script)

**Data Source**: [ISO 639-3 SIL](https://iso639-3.sil.org/)

**Documentation**: [docs/langs.md](docs/langs.md)

### 5. Identifiers Module ([rigour/ids/](rigour/ids/))

**Purpose**: Validation and formatting of corporate, tax, and other identifiers.

**Key Files**:
- [common.py](rigour/ids/common.py): `IdentifierFormat` base class
- [strict.py](rigour/ids/strict.py): `StrictFormat` for strict validation
- [wikidata.py](rigour/ids/wikidata.py): `WikidataQID` format
- [stdnum_.py](rigour/ids/stdnum_.py): Wrappers for python-stdnum formats
- [ogrn.py](rigour/ids/ogrn.py): Russian OGRN format
- [imo.py](rigour/ids/imo.py): IMO ship numbers
- [npi.py](rigour/ids/npi.py): US National Provider Identifier
- [uei.py](rigour/ids/uei.py): US Unique Entity Identifier

**Supported Identifier Types**:
- **Wikidata QID**: Wikidata identifiers (Q12345)
- **OGRN**: Russian organization registration numbers
- **IMO**: International Maritime Organization ship numbers
- **ISIN**: International Securities Identification Numbers
- **IBAN**: International Bank Account Numbers
- **FIGI/OpenFIGI**: Financial Instrument Global Identifiers
- **BIC/SWIFT**: Bank Identifier Codes
- **INN**: Russian tax identification numbers
- **NPI**: US healthcare provider identifiers
- **LEI**: Legal Entity Identifiers
- **UEI**: US government contractor identifiers
- **SSN**: US Social Security Numbers
- **CPF/CNPJ**: Brazilian personal/corporate tax IDs
- **USCC**: Chinese Unified Social Credit Codes

**Key Functions**:
- `get_identifier_format()`: Get format class by name
- `get_identifier_formats()`: List all formats
- `get_identifier_format_names()`: List format names
- `get_strong_format_names()`: List strong (high-confidence) formats

**Format Methods** (per identifier type):
- `validate()`: Check if value matches format
- `normalize()`: Convert to canonical form
- `format()`: Human-readable display format

**Documentation**: [docs/ids.md](docs/ids.md)

### 6. MIME Types Module ([rigour/mime/](rigour/mime/))

**Purpose**: Internet MIME type parsing and normalization.

**Key Files**:
- [parse.py](rigour/mime/parse.py): `MIMEType` class for MIME type objects
- [mime.py](rigour/mime/mime.py): MIME type normalization functions
- [filename.py](rigour/mime/filename.py): `FileName` class and extension handling
- [types.py](rigour/mime/types.py): MIME type definitions

**Key Functions**:
- `parse_mimetype()`: Parse MIME string to `MIMEType` object
- `normalize_mimetype()`: Normalize MIME type strings
- `useful_mimetype()`: Check if MIME type is useful (not generic)
- `normalize_extension()`: Normalize file extensions
- `mimetype_extension()`: Get extension for MIME type

**Features**:
- Handles malformed/invalid MIME types
- Human-readable labels for MIME types
- Family/subtype parsing
- File extension mapping

**Note**: This module is an inlined version of the standalone `pantomime` library.

**Documentation**: [docs/mime.md](docs/mime.md)

### 7. URLs Module ([rigour/urls/](rigour/urls/))

**Purpose**: URL cleaning, normalization, and comparison.

**Key Files**:
- [cleaning.py](rigour/urls/cleaning.py): URL cleaning and construction
- [compare.py](rigour/urls/compare.py): URL comparison logic
- [util.py](rigour/urls/util.py): URL utilities and types

**Key Functions**:
- `clean_url()`: Clean and normalize URL
- `clean_url_compare()`: Clean URL for comparison
- `build_url()`: Construct URL from components
- `compare_urls()`: Compare two URLs for equivalence

**Documentation**: [docs/urls.md](docs/urls.md)

### 8. Text Processing Module ([rigour/text/](rigour/text/))

**Purpose**: String distance metrics, phonetic encoding, and text utilities.

**Key Files**:
- [distance.py](rigour/text/distance.py): String distance algorithms
- [phonetics.py](rigour/text/phonetics.py): Phonetic encoding
- [checksum.py](rigour/text/checksum.py): Text hashing
- [cleaning.py](rigour/text/cleaning.py): Text cleaning utilities

**Key Functions**:
- `levenshtein()`: Levenshtein edit distance
- `dam_levenshtein()`: Damerau-Levenshtein distance
- `levenshtein_similarity()`: Normalized similarity score
- `is_levenshtein_plausible()`: Quick plausibility check
- `jaro_winkler()`: Jaro-Winkler similarity
- `metaphone()`: Metaphone phonetic encoding
- `soundex()`: Soundex phonetic encoding
- `text_hash()`: Consistent text hashing
- `remove_bracketed_text()`: Remove parenthetical content
- `remove_emoji()`: Remove emoji characters

**Documentation**: [docs/text.md](docs/text.md)

### 9. Utility Modules

#### Time Utilities ([rigour/time.py](rigour/time.py))
- `utc_now()`: Current UTC datetime
- `naive_now()`: Naive UTC datetime
- `utc_date()`: Current UTC date
- `iso_datetime()`: Parse ISO 8601 datetime strings
- `datetime_iso()`: Convert datetime to ISO string

#### Units ([rigour/units.py](rigour/units.py))
- `normalize_unit()`: Normalize measurement units
- `UNITS`: Dictionary mapping unit variants to standard forms (supports multiple languages)

#### Boolean Utilities ([rigour/boolean.py](rigour/boolean.py))
- `bool_text()`: Convert boolean to 't'/'f' string
- `text_bool()`: Parse text to boolean

#### Core Utilities ([rigour/util.py](rigour/util.py))
- `resource_lock`: Global lock for resource-intensive operations
- `unload_module()`: Module unloading helper
- `gettext()`: i18n placeholder
- `list_intersection()`: Proper list intersection with duplicates
- Cache size constants: `MEMO_TINY`, `MEMO_SMALL`, `MEMO_MEDIUM`, `MEMO_LARGE`

**Documentation**: [docs/misc.md](docs/misc.md)

## Reference Data

The library includes extensive curated reference data in [resources/](resources/):

### Names Data ([resources/names/](resources/names/))

- **stopwords.yml**: Stopwords and prefixes to remove (Mr., Mrs., The, etc.)
- **org_types.yml**: Organization type mappings with three normalization modes:
  - Display normalization: User-facing cosmetic simplification (Aktiengesellschaft → AG)
  - Compare normalization: String comparison optimization (Sp. z o.o. → spzoo)
  - Generic normalization: Cross-language alignment (Aktiengesellschaft → JSC, ООО → LLC)
- **symbols.yml**: Cross-language term mappings (Holding, Technology, Group, etc.)
- **persons.txt**: Hundreds of thousands of person name part mappings across scripts

### Territories Data ([resources/territories/](resources/territories/))

Includes metadata for countries, sub-national jurisdictions (Delaware, Dubai), historical entities (Yugoslavia, USSR), and disputed territories (Transnistria, Crimea, Somaliland):

- Territory names (short/long form)
- Wikidata QIDs
- ISO 3166 codes
- Parent/child relationships
- Successor/predecessor relationships
- Regional classification
- Legal jurisdiction indicators

### Address Data ([resources/addresses/](resources/addresses/))

- **forms.yml**: Address keyword normalization mappings
- **formats.yml**: Country-specific address formatting templates (from OpenCageData)

### Language Data ([resources/langs/](resources/langs/))

- ISO 639 language code mappings (2-letter, 3-letter, names)

### Text Data ([resources/text/](resources/text/))

- Unicode script definitions and categories

**Documentation**: [docs/data.md](docs/data.md)

## Testing

**Test Framework**: pytest with coverage reporting
**Test Directory**: [tests/](tests/)
**Run Tests**: `make test` or `pytest --cov rigour --cov-report term-missing --cov-report html tests`

## Type Checking

**Type Checker**: mypy with strict mode
**Run**: `make typecheck` or `mypy --strict rigour`

## Documentation

**Documentation System**: MkDocs with Material theme and mkdocstrings
**Documentation Source**: [docs/](docs/)
**Build Documentation**: `make docs` or `mkdocs build -c -d site`
**Configuration**: [mkdocs.yml](mkdocs.yml)

**Available Documentation**:
- [docs/index.md](docs/index.md): Main documentation index
- [docs/names.md](docs/names.md): Names module API
- [docs/addresses.md](docs/addresses.md): Addresses module API
- [docs/territories.md](docs/territories.md): Territories module API
- [docs/langs.md](docs/langs.md): Languages module API
- [docs/ids.md](docs/ids.md): Identifiers module API
- [docs/mime.md](docs/mime.md): MIME types module API
- [docs/urls.md](docs/urls.md): URLs module API
- [docs/text.md](docs/text.md): Text processing module API
- [docs/misc.md](docs/misc.md): Miscellaneous utilities API
- [docs/data.md](docs/data.md): Reference data documentation

## Usage Philosophy

From the README:

> The underlying idea is that handling these sorts of descriptors is easy on first glance, but reveals a dizzying set of complexity when carried into production. This is why `rigour` consolidates implementations that have already met some edge cases and are well-tested.

The library follows a [Falsehoods Programmers Believe About Names](https://www.kalzumeus.com/2010/06/17/falsehoods-programmers-believe-about-names/) philosophy - recognizing that simple rules don't work for real-world data.

## Related Projects

- [FollowTheMoney](https://followthemoney.tech): Principal user of rigour
- [OpenSanctions](https://www.opensanctions.org/docs/opensource/): Open source sanctions data
- [OpenAleph](https://github.com/openaleph): Investigation toolkit ecosystem

## Acknowledgements

- **Address formatting database**: Derived from OpenCageData's [address-formatting](https://github.com/OpenCageData/address-formatting) repository
- **Cultural data contributions**: [github.com/confirmordeny](https://github.com/confirmordeny)
- **Funding**: OCCRP (Organized Crime and Corruption Reporting Project) as part of the Aleph software project

## Naming

From Jorge Luis Borges' "On Rigor in Science" - a meditation on the futility of perfect cartographic representation, reflecting the library's approach to handling real-world messiness with practical rigor rather than seeking impossible perfection.
