from rigour.text import metaphone, soundex

def test_metaphone():
    # rphonetic collapses whitespace; jellyfish preserved it. Production callers
    # always tokenize first (see rigour/names/part.py, nomenklatura phonetic.py),
    # so the collapsed form is what real code actually sees.
    assert metaphone('John Doe') == 'JNT'
    assert metaphone('John') == 'JN'
    assert metaphone('Doe') == 'T'

def test_soundex():
    assert soundex('John Doe') == 'J530'