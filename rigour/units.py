UNITS = {
    "centimeters": "cm",
    "centimetres": "cm",
    "centimeter": "cm",
    "meters": "m",
    "meter": "m",
    "metre": "m",
    "metres": "m",
    "lbs.": "lbs",
    "pound": "lbs",
    "pounds": "lbs",
    "kg": "kg",
    "kilograms": "kg",
    "inches": "in",
    "inch": "in",
    "feet": "ft",
    "foot": "ft",
    "grams": "g",
    "m2": "m²",
    "square meters": "m²",
    "square metres": "m²",
    "sqm": "m²",
    "hectare": "ha",
    "hectares": "ha",
    "tons": "t",
    "tonnes": "t",
    "eur": "€",
    "euro": "€",
    "euros": "€",
    "dollars": "$",
    "dollar": "$",
    "cents": "¢",
    "cent": "¢",
    "rub": "₽",
    "rubles": "₽",
    "ruble": "₽",
    "russian ruble": "₽",
    "russian rubles": "₽",
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
