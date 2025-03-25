# rigour

Data cleaning and validation functions for processing various types of text emanating and describing the business world. This applies to human and company names, language, territory
and country codes, corporate and tax identifiers, etc.

The underlying idea is that handling these sorts of descriptors is easy on first glance, but reveals a dizzying set of complexity when carried into production. This is why `rigour` consolidates implementations that have already met some edge cases and are well-tested.

## Installing `rigour`

You can just grab the library from PyPI:

```bash
pip install -U rigour
```

### Acknowledgements

The address formatting database contained in `rigour/data/addresses/formats.yml` is derived from `worldwide.yml` in the [OpenCageData address-formatting repository](https://github.com/OpenCageData/address-formatting). It is used to format addresses according to customs in the country that is been encoded.

## Usage & documentation 

See: https://opensanctions.github.io/rigour/


