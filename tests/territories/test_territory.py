from rigour.territories import get_territory, get_territory_by_qid
from rigour.territories import get_ftm_countries, get_territories
from rigour.territories.util import clean_codes


def test_world_real():
    gb = get_territory("gb")
    assert gb is not None
    assert gb.name == "United Kingdom"
    assert gb.parent is None
    assert gb.in_sentence == "the United Kingdom"
    assert gb.region == "Europe"
    assert gb.subregion == "Northern Europe"
    assert "parent" not in gb.to_dict()
    assert get_territory_by_qid("Q145") == gb
    assert gb.qid == "Q145"
    assert "Q145" in gb.to_dict()["qids"]
    assert get_territory_by_qid("Q2914461") == get_territory("ge-ab")
    abk = get_territory("ge-ab")
    assert abk is not None
    assert abk.in_sentence == abk.name
    assert abk.qid != "Q2914461"
    nir = get_territory("gb-nir")
    assert nir is not None
    assert nir.parent == gb
    assert nir.to_dict()["parent"] == "gb"
    assert get_territory("gb-nirvana") is None
    assert get_territory_by_qid("Q232323312") is None

    cq = get_territory("cq")
    srk = get_territory("gg-srk")
    assert cq is not None
    assert srk is not None
    assert srk == cq
    assert "gg-srk" in cq.to_dict()["codes"]

    su = get_territory("su")
    assert su is not None
    assert get_territory("ru") in su.successors
    assert get_territory("ru") in su.see

    nir = get_territory("gb-nir")
    assert nir is not None
    assert nir.in_sentence == "Northern Ireland"
    assert nir.region == "Europe"
    assert nir.subregion == "Northern Europe"

    moscow = get_territory("ru-mos")
    assert moscow is not None
    assert moscow._region is None
    assert moscow.region == "Europe"
    assert moscow.subregion == "Eastern Europe"
    assert moscow.is_ftm is False
    assert moscow.ftm_country == "ru"


def test_territory_class_functions():
    fr = get_territory("fr")
    assert fr is not None
    assert repr(fr) == "<Territory('fr')>"

    assert fr == get_territory("fr")
    assert fr != get_territory("de")
    assert hash(fr) == hash(get_territory("fr"))
    assert hash(fr) != hash(get_territory("de"))

    assert fr.region == "Europe"
    assert fr.subregion == "Western Europe"

    assert fr != "fr"
    assert fr > get_territory("de")
    assert fr < "fr"

    dubai = get_territory("ae-du")
    assert dubai is not None
    assert dubai.region == "Asia"
    assert dubai.subregion == "Western Asia"


def test_territory_ftm():
    ae = get_territory("ae")
    assert ae is not None
    assert ae.ftm_country == "ae"

    dubai = get_territory("ae-du")
    assert dubai is not None
    assert dubai.ftm_country == "ae"

    crimea = get_territory("ua-cri")
    assert crimea is not None
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
    assert len(territories) < 1000
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


def test_clean_code():
    assert clean_codes(["GB", "US", "FR"]) == ["gb", "us", "fr"]
    assert clean_codes(["GB_NIR"]) == ["gb-nir"]
    assert clean_codes([""]) == []
