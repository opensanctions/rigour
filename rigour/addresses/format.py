import yaml
from typing import Dict, Optional, TypedDict
from functools import cache
from jinja2 import Template, Environment

from rigour.data import DATA_PATH
from rigour.env import ENCODING
from rigour.addresses.cleaning import clean_address

env = Environment()


class Format(TypedDict):
    address_template: str
    use_country: str
    change_country: str
    add_component: Dict[str, str]


@cache
def load_formats() -> Dict[str, Format]:
    template_file = DATA_PATH / "addresses" / "formats.yml"
    with open(template_file, "r", encoding=ENCODING) as fp:
        data: Dict[str, Format] = yaml.load(fp, Loader=yaml.FullLoader)
    return data


@cache
def load_template(template: str) -> Template:
    return env.from_string(template)


def _format(address: Dict[str, Optional[str]], country: Optional[str] = None) -> str:
    country = country.upper()
    formats = load_formats()
    fmt = formats.get(country)
    if fmt is None and "-" in country:
        country, _ = country.split("-", 1)
        fmt = formats.get(country)
    if fmt is None:
        fmt = formats.get("default", None)
    if fmt is None:
        raise RuntimeError("Missing the default address model!")

    # Some country configurations redirect to other countries but
    # change the country name in the process:
    use_country = fmt.get("use_country")
    if use_country is not None:
        country = fmt.get("change_country")
        if country is not None:
            address["country"] = country
        address.update(fmt.get("add_component", {}))
        return _format(address, country=use_country)

    cleaned_address: Dict[str, str] = {}
    for key, value in address.items():
        if value is None:
            continue
        value = value.strip()
        if len(value):
            cleaned_address[key] = value

    tpl_str = fmt.get("address_template")
    tpl = load_template(tpl_str)
    return tpl.render(**cleaned_address)


def format(address: Dict[str, Optional[str]], country: Optional[str] = None) -> str:
    return clean_address(_format(address, country=country))


def format_one_line(
    address: Dict[str, Optional[str]], country: Optional[str] = None
) -> str:
    line = ", ".join(_format(address, country=country).split("\n"))
    return clean_address(line)
