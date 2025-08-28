from rigour.text.checksum import text_hash


def test_text_hash():
    assert text_hash("Hello, World!") == "6adfb183a4a2c94a2f92dab5ade762a47889a5a1"
    assert text_hash("HelloWorld") == text_hash("Hello, World!")
    assert text_hash("Rigour\n\t!!!!!!!") == text_hash("rigour")
    assert text_hash("") == text_hash(". ")
    assert False
