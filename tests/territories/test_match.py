from rigour.territories.match import territories_intersect


def test_territories_intersect_basic():
    common = territories_intersect(["us", "ca"], ["mx", "ca", "us"])
    assert common == {"us", "ca"}
    none = territories_intersect(["us", "ca"], ["mx", "fr"])
    assert none == set()
    none = territories_intersect([], ["mx", "fr"])
    assert none == set()


def test_territories_intersect_code_norm():
    common = territories_intersect(["cn-hk"], ["hk"])
    assert common == {"hk"}


def test_territories_intersect_children():
    common = territories_intersect(["us"], ["us-ca", "us-tx"])
    assert common == {"us-ca", "us-tx"}

    # Kinky geopolitics for 500:
    common = territories_intersect(["ru"], ["ua-cri"])
    assert common == {"ua-cri"}

    common = territories_intersect(["ua-cri"], ["ru"])
    assert common == {"ua-cri"}

    common = territories_intersect(["ua"], ["ua-cri"])
    assert common == {"ua-cri"}

    common = territories_intersect(["ua-cri"], ["ua"])
    assert common == {"ua-cri"}

    common = territories_intersect(["ge"], ["x-so"])
    assert common == {"x-so"}

    common = territories_intersect(["ru"], ["x-so"])
    assert common == {"x-so"}

    common = territories_intersect(["cn"], ["hk"])
    assert common == {"hk"}

    common = territories_intersect(["md"], ["md-pmr"])
    assert common == {"md-pmr"}
