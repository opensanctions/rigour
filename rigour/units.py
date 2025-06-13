UNITS = {
    # Length
    "centimeters": "cm", # en-US
    "centimetres": "cm",
    "centimeter": "cm", # en-US
    "centimetre": "cm",
    "meters": "m", # en-US
    "metres": "m", 
    "meter": "m", # en-US
    "metre": "m", 
    "kilometers": "km", # en-US
    "kilometres": "km", 
    "kilometer": "km", # en-US
    "kilometre": "km", 
    "inches": "in",
    "inch": "in",
    "″": "in", # double prime symbol (unicode: U+2033) — the correct unicode symbol for inches (in practice people may use double quotes etc)
    "feet": "ft",
    "foot": "ft",
    "′": "ft", # prime symbol (unicode: U+2032) — the correct unicode symbol for feet (in practice people may use single quote etc)
    # Weight/mass
    "grams": "g",
    "grammes": "g", # en-GB
    "lbs.": "lbs",
    "pound": "lbs",
    "pounds": "lbs",
    "kg": "kg",
    "kilograms": "kg",
    "kilogrammes": "kg", # en GB
    "kilos": "kg",
    "ton": "t",
    "tons": "t",
    "tonne": "t",
    "tonnes": "t",
    "metric ton": "t",
    "metric tonne": "t",
    "metric tons": "t",
    "metric tonnes": "t",
    # Area
    "m2": "m²",
    "square meters": "m²", # en-US
    "square metres": "m²",
    "sqm": "m²",
    "hectares": "ha",
    "hectare": "ha",
    # Volume
    "cubic feet": "cf",
    "cubic ft": "cf",
    # Time/frequency
    "seconds": "s",
    "secs": "s",
    "millisecond": "ms",
    "milliseconds": "ms",
    "hertz": "Hz",
    # Currency
    # (i) Currency — whole units 
    "eur": "€",
    "euros": "€",
    "euro": "€",
    "dollars": "$",
    "dollar": "$",
    "British pounds": "£", # Note: 'pounds' can also be a unit of weight
    "British pound": "£", 
    "pounds sterling": "£", 
    "pound sterling": "£", 
    "rub": "₽",
    "rubles": "₽",
    "ruble": "₽",
    "russian rubles": "₽",
    "russian ruble": "₽",
    # (ii) Currency — fractions of units
    "cents": "¢",
    "cent": "¢",
    "centimes": "¢",
    "centime": "¢",
    "pence": "p",
    "penny": "p",
}


def normalize_unit(unit: str) -> str:
    """
    Normalize a unit string to its standard abbreviation.

    Args:
        unit (str): The unit string to normalize.

    Returns:
        str: The normalized unit abbreviation.
    """
    return UNITS.get(unit.lower(), unit)
