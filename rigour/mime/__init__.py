"""
This module handles the parsing and normalisation of internet MIME types in Python. This can be useful
to normalise invalid, or misformatted MIME types emitted by remote web servers.

## Usage

The simplest use is to normalise a MIME type:

```python
from rigour.mime import normalize_mimetype

assert normalize_mimetype('TEXT/PLAIN') == 'text/plain'
assert normalize_mimetype('plain/text') == 'text/plain'
assert normalize_mimetype(None) == 'application/octet-stream'
assert normalize_mimetype('') == 'application/octet-stream'
```

Internally, `rigour.mime` uses a `MIMEType` object to handle parsing. It can be used to access more
specific information, like human readable labels:

```python
from rigour.mime import parse_mimetype

parsed = parse_mimetype('text/plain')
assert parsed.family == 'text'
assert parsed.subtype == 'plain'
assert parsed.label == 'Plain text'
```

## Open issues

* Internationalisation, i.e. make the human-readable labels available in multiple languages.
* Expand replacements for specific MIME types.

This module is an inlined version of the `pantomime` library.
"""

from rigour.mime.parse import MIMEType
from rigour.mime.types import DEFAULT, PLAIN
from rigour.mime.mime import parse_mimetype, normalize_mimetype
from rigour.mime.mime import useful_mimetype
from rigour.mime.filename import FileName
from rigour.mime.filename import normalize_extension, mimetype_extension

__all__ = [
    "MIMEType",
    "FileName",
    "DEFAULT",
    "PLAIN",
    "parse_mimetype",
    "normalize_mimetype",
    "useful_mimetype",
    "normalize_extension",
    "mimetype_extension",
]
