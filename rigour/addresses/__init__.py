"""
This module provides a set of tools for handling postal/geographic addresses. It includes functions
for normalising addresses for comparison purposes, and for formatting addresses given in parts for
display as a single string.

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
from rigour.addresses.normalize import normalize_address
from rigour.addresses.normalize import remove_address_keywords, shorten_address_keywords
from rigour.addresses.format import format_address, format_address_line

__all__ = [
    "clean_address",
    "normalize_address",
    "remove_address_keywords",
    "shorten_address_keywords",
    "format_address",
    "format_address_line",
]
