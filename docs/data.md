# Core reference data

## Territories

The [database of territories](https://github.com/opensanctions/rigour/tree/main/resources/territories) includes countries, sub-country jurisdictions (think: Delaware, Dubai), some historical jurisdictions (think: Yugoslavia, USSR) and disputed territories (think: Transnistria, Crimea, Somaliland). Metadata for each jurisidiction includes:

* Territory names in short and long form, name of region and subregion.
* Corresponding Wikidata QID, and alternate Wikidata QIDs for similar items.
* Relationship to other territories (parent/child, successor/predecessor, see also).
* ISO 3166-2 codes where applicable, including previous codes and custom country codes for unrecognized territories.
* Tags on whether a territory is a country or jurisdiction.

## Addresses

This library does not perform geocoding and treats address matching as a text comparison, and not a geodesic problem. In order to allow for better string comparison between two address strings, we include an alias mapping file which re-writes common terms used in addresses to increase the chance of a string match (eg. "Street" -> "St"). 

* [forms.yml](https://github.com/opensanctions/rigour/blob/main/resources/addresses/forms.yml)

See also: 
* [libpostal](https://github.com/openvenues/libpostal) is a fully developed C library for address parsing and normalisation that is trained on OpenStreetMap data.
* [addressformatting](https://github.com/OpenCageData/address-formatting) solves the inverse problem: given a set of address components (like street, city, postal code), it will create a text representation that is in line with local expectations in the given country.