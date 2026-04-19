from rigour.text.dictionary import Scanner


def test_scanner():
    forms = ["hello", "world"]
    scanner = Scanner(forms)

    # Test extraction
    text = "hello world"
    extracted = scanner.extract(text)
    assert extracted == ["hello", "world"]

    # Test removal
    removed = scanner.remove(text)
    assert len(removed.strip()) == 0

    scanner = Scanner(["Ban", "Banana", "Long Banana"], ignore_case=False)
    found = scanner.extract("I am a Banana!")
    assert found == ["Banana"]

    found = scanner.extract("I'm a banana!")
    assert found == []

    # Escapes
    scanner = Scanner(["C.I.A.", "Space Invaders"])
    found = scanner.extract("The Space Invaders are run by the C.I.A.")
    assert "C.I.A." in found
    assert "Space Invaders" in found
