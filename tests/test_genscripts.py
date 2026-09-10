import pytest

from genscripts.generate_territories import check_name_collisions


def test_check_name_collisions():
    check_name_collisions({"iran": {("ir", "name"), ("ir", "names_weak")}})
    check_name_collisions({})

    claims = {
        "tehran": {("ir", "places")},
        "london": {("gb-eng", "places"), ("ca-on", "places")},
        "georgia": {("ge", "name"), ("us-ga", "names_weak")},
    }
    with pytest.raises(RuntimeError, match="2 territory name collisions"):
        check_name_collisions(claims)
