from rigour.names.compare import align_name_parts


def test_align_name_parts():
    assert align_name_parts(["John", "Doe"], ["John", "Doe"]) == [
        ("John", "John"),
        ("Doe", "Doe"),
    ]
    assert align_name_parts(["John", "Doe"], ["Doe", "John"]) == [
        ("John", "John"),
        ("Doe", "Doe"),
    ]
    assert align_name_parts(["John", "Doe"], ["Doe"]) == [("Doe", "Doe"), ("John", "")]
    assert align_name_parts(["John", "Doe"], []) == [("John", ""), ("Doe", "")]
    assert align_name_parts([], ["John", "Doe"]) == [("", "John"), ("", "Doe")]
    assert align_name_parts(["John", "Doe"], ["John", "Doe", "Smith"]) == [
        ("John", "John"),
        ("Doe", "Doe"),
        ("", "Smith"),
    ]
    assert align_name_parts(["John", "Doe", "Smith"], ["John", "Doe"]) == [
        ("John", "John"),
        ("Doe", "Doe"),
        ("Smith", ""),
    ]
    aligned = align_name_parts(["John", "Doex", "Smith"], ["Doe", "Smith"])
    assert aligned[-1][0] == "John", aligned

    aligned = align_name_parts(
        ["Vladimir", "Vladimiric", "Putin"], ["Vladimir", "Putin"]
    )
    assert aligned[-1][0] == "Vladimiric", aligned
