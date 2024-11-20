import yaml
from typing import Dict, Optional, TypedDict
from functools import cache, lru_cache
from jinja2 import Template, Environment

from rigour.data import DATA_PATH
from rigour.env import ENCODING
from rigour.addresses.cleaning import clean_address

env = Environment()


class Format(TypedDict):
    address_template: str
    use_country: str
    add_component: Dict[str, str]


@cache
def _load_formats() -> Dict[str, Format]:
    template_file = DATA_PATH / "addresses" / "formats.yml"
    with open(template_file, "r", encoding=ENCODING) as fp:
        data: Dict[str, Format] = yaml.load(fp, Loader=yaml.FullLoader)
    return data


@cache
def _load_template(template: str) -> Template:
    return env.from_string(template)


def _format(address: Dict[str, Optional[str]], country: Optional[str] = None) -> str:
    country = country.upper()
    formats = _load_formats()
    fmt = formats.get(country)
    if fmt is None and "-" in country:
        country, _ = country.split("-", 1)
        fmt = formats.get(country)
    if fmt is None:
        fmt = formats.get("default", None)
    if fmt is None:
        raise RuntimeError("Missing the default address model!")  # pragma: nocover

    # Some country configurations redirect to other countries but
    # change the country name in the process:
    use_country = fmt.get("use_country")
    if use_country is not None:
        for key, value in fmt.get("add_component", {}).items():
            if key not in address:
                address[key] = value
        return _format(address, country=use_country)

    cleaned_address: Dict[str, str] = {}
    for key, value in address.items():
        if value is None:
            continue
        value = value.strip()
        if len(value):
            cleaned_address[key] = value

    tpl_str = fmt.get("address_template")
    tpl = _load_template(tpl_str)
    return tpl.render(**cleaned_address)


@lru_cache(maxsize=20000)
def format(address: Dict[str, Optional[str]], country: Optional[str] = None) -> str:
    return clean_address(_format(address, country=country))


@lru_cache(maxsize=20000)
def format_one_line(
    address: Dict[str, Optional[str]], country: Optional[str] = None
) -> str:
    """Format the given address part into a single-line string that matches the
    conventions of the country of the given address.

    Args:
        address: The address parts to be combined. Common parts include:
            summary: A short description of the address.
            po_box: The PO box/mailbox number.
            street: The street or road name.
            house: The descriptive name of the house.
            house_number: The number of the house on the street.
            postal_code: The postal code or ZIP code.
            city: The city or town name.
            county: The county or district name.
            state: The state or province name.
            state_district: The state or province district name.
            state_code: The state or province code.
            country: The name of the country (words, not ISO code).
            country_code: A pre-normalized country code.
        country: ISO code for the country of the address.

    Returns:
        A single-line string with the formatted address.
    """
    line = ", ".join(_format(address, country=country).split("\n"))
    return clean_address(line)
