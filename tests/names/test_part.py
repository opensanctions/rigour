from rigour.names import name_parts
from rigour.names.part import NamePart


def test_name_parts():
    assert name_parts('John Doe')[0].ascii == 'john'
    assert name_parts('John Doe')[1].ascii == 'doe'
    assert name_parts('John Doe')[0].index == 0
    assert name_parts('C.I.A.')[0].ascii == 'cia'

    assert name_parts('Sir Patrick Stewart')[0].ascii == 'patrick'
    assert name_parts('Sir Patrick Stewart', person=False)[0].ascii == 'sir'


def test_name_part():
    john = NamePart('John', 0)
    assert john.ascii == 'john'
    assert john.lower == 'john'
    assert john.is_alphabet is True
    assert len(john) == 4
    assert hash(john) == hash('john')
    assert john == NamePart('John', 0)
    assert john == NamePart('John', 1)
    assert repr(john) == '<NamePart(John, 0)>'

    petro = NamePart('Петро́', 0)
    assert petro.ascii == 'petro'
    assert petro.metaphone == 'PTR'
    assert petro != john
    assert petro != 3

    osama = NamePart('أسامة', 0)
    assert osama.ascii == 'asamt'
    assert osama.is_alphabet is False
    assert osama.metaphone is None