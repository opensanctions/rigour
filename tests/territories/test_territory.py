from rigour.territories import get_territory, get_territory_by_qid
from rigour.territories import get_ftm_countries, get_territories


def test_world_real():
    gb = get_territory("gb")
    assert gb.name == "United Kingdom"
    assert gb.parent is None
    assert get_territory_by_qid("Q145") == gb
    assert gb.qid == "Q145"
    assert get_territory_by_qid("Q2914461") == get_territory("ge-ab")
    assert get_territory("ge-ab").qid != "Q2914461"
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

    countries = get_ftm_countries()
    assert len(countries) > 200
    assert len(countries) < 400
    for terr in countries:
        assert terr.is_ftm
        assert terr.ftm_country == terr.code


def test_list_access():
    territories = get_territories()
    assert len(territories) > 200
    assert len(territories) < 400
    for terr in territories:
        assert terr == get_territory(terr.code)
        assert terr == get_territory_by_qid(terr.qid)
        for qid in terr.qids:
            assert terr == get_territory_by_qid(qid)
        for qid in terr.other_qids:
            assert terr == get_territory_by_qid(qid)
        for code in terr.other_codes:
            assert terr == get_territory(code)
        for see in terr.see:
            assert see in territories
