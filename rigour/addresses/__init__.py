"""
# Postal/location address handling

This set of helpers is designed to help with the processing of real-world
addresses, including composing an address from individual parts, and cleaning it up.

```python
import rigour.addresses as format_one_line

address = {
    "road": "Bahnhofstr.",
    "house_number": "10",
    "postcode": "86150",
    "city": "Augsburg",
    "state": "Bayern",
    "country": "Germany",
}
address_text = format_one_line(address, country="DE")
```
"""

from rigour.addresses.cleaning import clean_address
from rigour.addresses.format import format_address, format_address_line

__all__ = ["clean_address", "format_address", "format_address_line"]
