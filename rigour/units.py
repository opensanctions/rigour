UNITS = {
    # Fractions
    "percent": "%",
    "pct": "%",
    "pct.": "%",
    "percentage": "%",
    "per cent": "%",
    "per-cent": "%",
    "pour cent": "%", # fr
    "pourcentage": "%", # fr
    "porcentaje": "%", # es
    "por ciento": "%", # es
    "porcentagem": "%", # pt
    "percentuale": "%", # it
    "procentas": "%", # lt
    "procenti": "%", # lv
    "prosent": "%", # no
    "prosentti": "%", # fi
    "protsent": "%", # et
    "prozentsatz": "%", # de (percentage rate)
    "prozent": "%", # de
    "procent": "%", # da, nl, pl, sv
    "százalék": "%", # hu
    "процент": "%", # ru
    "відсоток": "%", # uk
    "نسبة مئوية": "%", # ar
    "パーセント": "%", # ja
    "百分之": "%", # zh
    "프로": "%", # ko
    "퍼센트": "%", # ko
    # Length
    "centimeters": "cm",  # en-US
    "centimetres": "cm",
    "centimeter": "cm",  # en-US
    "centimetre": "cm",
    "centimètre": "cm", # fr (singular)
    "centimètres": "cm", # fr (plural)
    "centímetro": "cm", # es, pt (singular)
    "centímetros": "cm", # es, pt (plural)
    "meters": "m",  # en-US
    "metres": "m",
    "meter": "m",  # en-US
    "metre": "m",
    "mètre": "m", # fr (singular)
    "mètres": "m", # fr (plural)
    "метр": "m", # ru, uk (singular)
    "метры": "m", # ru (plural)
    "метрів": "m", # uk (plural)
    "متر": "m", # ar
    "미터": "m", # ko
    "kilometers": "km",  # en-US
    "kilometres": "km",
    "kilometer": "km",  # en-US
    "kilometre": "km",
    "kilomètre": "km", # fr (singular)
    "kilomètres": "km", # fr (plural)
    "kilómetro": "km", # es (singular)
    "kilómetros": "km", # es (plural)
    "quilômetro": "km", # pt  (singular)
    "quilômetros": "km", # pt (plural)
    "inches": "in", # en (plural)
    "inch": "in", # en (singular)
    "pulgada": "in", # es (singular)
    "pulgadas": "in", # es (plural)
    "polegada": "in", # pt (singular)
    "polegadas": "in", # pt (plural)
    "pouce": "in", # fr (singular)
    "pouces": "in", # fr (plural)
    "дюйм": "in", # ru, uk (singular)
    "дюймів": "in", # uk (plural)
    "дюймы": "in", # ru (plural)
    "″": "in",  # double prime symbol (unicode: U+2033) — the correct unicode symbol for inches (in practice people may use double quotes etc)
    "feet": "ft",
    "foot": "ft",
    "′": "ft",  # prime symbol (unicode: U+2032) — the correct unicode symbol for feet (in practice people may use single quote etc)
    # Weight/mass
    "grams": "g",
    "grammes": "g",  # en-GB
    "gramm": "g", # de
    "lbs.": "lbs",
    "pound": "lbs",
    "pounds": "lbs",
    "kg": "kg",
    "kgs": "kg",
    "kilograms": "kg",
    "kilogrammes": "kg",  # en-GB
    "kilogramm": "kg", # de
    "kilos": "kg",
    "ton": "t",
    "tons": "t",
    "tonne": "t",
    "tonnes": "t",
    "tonnen": "t", # de
    "metric ton": "t",
    "metric tonne": "t",
    "metric tons": "t",
    "metric tonnes": "t",
    # Area
    "m2": "m²",
    "square meters": "m²",  # en-US
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
    "gbp": "£", # currency code
    "british pounds": "£",  # Note: 'pounds' can also be a unit of weight
    "british pound": "£",
    "pounds sterling": "£",
    "pound sterling": "£",
    "livres sterling": "£", # fr
    "pfund sterling": "£", # de
    "￡": "£", # This maps the fullwidth pound sign (U+FFE1) to the pound sign (U+00A3)
    "rub": "₽",
    "rubles": "₽",
    "ruble": "₽",
    "russian rubles": "₽",
    "russian ruble": "₽",
    "indian rupee": "₹",
    "indian rupees": "₹",
    "₹": "₹",
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
