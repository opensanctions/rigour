from rigour.territories import get_territory, get_territory_by_qid


def test_world_real():
    gb = get_territory("gb")
    assert gb.name == "United Kingdom"
    assert get_territory_by_qid("Q145") == gb
    nir = get_territory("gb-nir")
    assert nir is not None
    assert nir.parent == gb
    assert get_territory("gb-nirvana") is None

    cq = get_territory("cq")
    srk = get_territory("gg-srk")
    assert cq is not None
    assert srk is not None
    assert srk == cq

    su = get_territory("su")
    assert get_territory("ru") in su.successors
    assert get_territory("ru") in su.see


def test_territory_class_functions():
    fr = get_territory("fr")
    assert repr(fr) == "<Territory('fr')>"

    assert fr == get_territory("fr")
    assert fr != get_territory("de")
    assert hash(fr) == hash(get_territory("fr"))
    assert hash(fr) != hash(get_territory("de"))

    assert fr != "fr"
    assert fr > get_territory("de")


def test_territory_ftm():
    ae = get_territory("ae")
    assert ae.ftm_country == "ae"

    dubai = get_territory("ae-du")
    assert dubai.ftm_country == "ae"

    crimea = get_territory("ua-cri")
    assert crimea.ftm_country == "ua-cri"

    # antilles = get_territory("anhh")
    # assert antilles.ftm_country is None
