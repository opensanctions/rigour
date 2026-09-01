"""
This module provides a set of tools for handling postal/geographic addresses. It includes functions
for comparing addresses, normalising them, and for formatting addresses given in parts for
display as a single string.

## Address comparison

Score whether two address strings (or two sets of them) denote the
same place:

```python
from rigour.addresses import compare_address, compare_address_many

score = compare_address("Bahnhofstr. 10, Augsburg", "Bahnhofstrasse 10, 86150 Augsburg")
best = compare_address_many(
    ["Bahnhofstr. 10, Augsburg"],
    ["Bahnhofstrasse 10, 86150 Augsburg", "P.O. Box 71, Augsburg"],
)
```

The comparison runs in native code over analyzed tokens — see
[compare_address][rigour.addresses.compare.compare_address] for the
mechanics and score semantics.

The same analysis backs a keying surface: use
[address_fingerprint][rigour.addresses.compare.address_fingerprint]
to reduce equivalent renderings of an address to one deterministic
string for deduplication or graph node identity:

```python
from rigour.addresses import address_fingerprint

key = address_fingerprint("Main Boulevard 5, Syrian Arab Republic")
# "main blvd 5 sy" — same key as for "Main Blvd. 5, Syria"
```

## Postal address formatting

This set of helpers is designed to help with the processing of real-world
addresses, including composing an address from individual parts, and cleaning it up.

```python
from rigour.addresses import format_address_line

address = {
    "road": "Bahnhofstr.",
    "house_number": "10",
    "postcode": "86150",
    "city": "Augsburg",
    "state": "Bayern",
    "country": "Germany",
}
address_text = format_address_line(address, country="DE")
```

### Acknowledgements

The address formatting database contained in `rigour/data/addresses/formats.yml` is
derived from `worldwide.yml` in the [OpenCageData address-formatting
repository](https://github.com/OpenCageData/address-formatting). It is used to
format addresses according to customs in the country that is been encoded.
"""

from rigour.addresses.cleaning import clean_address
from rigour.addresses.compare import (
    address_fingerprint,
    compare_address,
    compare_address_many,
)
from rigour.addresses.format import format_address, format_address_line
from rigour.addresses.normalize import (
    normalize_address,
    remove_address_keywords,
    shorten_address_keywords,
)

__all__ = [
    "address_fingerprint",
    "clean_address",
    "compare_address",
    "compare_address_many",
    "format_address",
    "format_address_line",
    "normalize_address",
    "remove_address_keywords",
    "shorten_address_keywords",
]
