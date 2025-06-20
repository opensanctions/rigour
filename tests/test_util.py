from rigour.util import list_intersection


def test_list_intersection():
    """Test the list_intersection function."""
    assert list_intersection([], []) == []
    assert list_intersection(["a"], ["a"]) == ["a"]
    assert list_intersection(["a", "a"], ["a", "a"]) == ["a", "a"]
    assert list_intersection(["a", "b"], ["b", "c"]) == ["b"]
    assert list_intersection(["a", "b", "b"], ["b", "b", "c"]) == ["b", "b"]
    assert list_intersection(["a", "b", "c"], ["d", "e"]) == []
    assert list_intersection(["a", "b", "c"], ["c", "d"]) == ["c"]
    assert list_intersection(["a", "b"], ["a", "b"]) == ["a", "b"]
