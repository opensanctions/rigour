This library contains data validation and cleaning routines that are meant to be precise. These methods are supported by resource data. The resource data is derived from real-world datasets and meant to cover common cases of data variations in corporate registries, and AML/KYC screening data.

## Precision

* When supplementing the YAML resources in this directory, always prioritise precision over quantity.
* In alias/symbol mappings, make sure to include only aliases that would be commonly used in a business database.
* In mappings where common misspellings or variations are supplied, propose variants found in contractual documents, such as partial abbreviations, misspellings, simplifications, etc.

## Languages

* Our resources should target always supporting the following languages: English, French, Spanish, Russian, Ukrainian, Arabic, Simplified Chinese, Korean, Japanese, Portuguese (Brazilian and European), Turkish, Polish, German, Swedish, Norwegian, Danish, Lithuanian, Estonian, Finnish, Hungarian, Dutch

## Python 

* Generate fully-typed, minimal Python code.
* Always explicitly check `if x is None:`, not `if x:`
* Run tests using `pytest --cov rigour`
* Run typechecking using `mypy --strict rigour`