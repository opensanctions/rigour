from rigour.text import metaphone, soundex

def test_metaphone():
    assert metaphone('John Doe') == 'JN T'

def test_soundex():
    assert soundex('John Doe') == 'J530'