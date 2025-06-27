from normality import collapse_spaces
import pytest

from rigour.addresses import (
    normalize_address,
    remove_address_keywords,
    shorten_address_keywords,
)
from rigour.text.dictionary import Replacer, AhoCorReplacer


@pytest.mark.parametrize("clazz", [Replacer, AhoCorReplacer])
def test_normalize_address(clazz):
    address = "Bahnhofstr. 10, 86150 Augsburg, Germany"
    assert normalize_address(address) == "bahnhofstr 10 86150 augsburg germany"

    address = "160 Broad St, Birmingham B15 1DT"
    assert normalize_address(address) == "160 broad st birmingham b15 1dt"

    address = "160 Broad` St, Birmingham B15 1DT"
    assert normalize_address(address) == "160 broad st birmingham b15 1dt"

    address = "160 Broad Street, Birmingham B15 1DT"
    normalized = normalize_address(address)
    assert shorten_address_keywords(normalized) == "160 broad st birmingham b15 1dt"
    removed = collapse_spaces(remove_address_keywords(normalized, replacer_class=clazz))
    assert removed == "160 broad birmingham b15 1dt"

    address = "Marlborough House, Pall Mall, London SW1Y 5HX"
    normalized = normalize_address(address)
    assert normalized == "marlborough house pall mall london sw1y 5hx"
    removed = collapse_spaces(remove_address_keywords(normalized, replacer_class=clazz))
    assert removed == "marlborough pall mall london sw1y 5hx"

    assert normalize_address("hey") is None
    assert normalize_address("") is None
    assert normalize_address("h e") is None

    assert (
        normalize_address("Д.127, АМУРСКАЯ, АМУРСКАЯ, 675000")
        == "д 127 амурская амурская 675000"
    )
    assert (
        normalize_address("Д.127, АМУРСКАЯ, АМУРСКАЯ, 675000", latinize=True)
        == "d 127 amurskaa amurskaa 675000"
    )
