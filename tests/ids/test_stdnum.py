from rigour.ids import IMO, ISIN, IBAN, FIGI, BIC, INN, LEI, CPF, CNPJ


def test_imo():
    assert IMO.is_valid("IMO 9126819")
    assert IMO.is_valid("9126819")
    assert IMO.normalize("IMO 9126819") == "9126819"
    assert not IMO.is_valid("IMO 9126")
    assert not IMO.is_valid("9126")
    assert not IMO.is_valid("")


def test_isin():
    assert ISIN.is_valid("US0378331005")
    assert not ISIN.is_valid("0378331005")
    assert not ISIN.is_valid("XX0378331005")
    assert not ISIN.is_valid("US037833100")
    assert not ISIN.is_valid("037833100")
    assert not ISIN.is_valid("")
    assert ISIN.format("us0378331005") == "US0378331005"


def test_iban():
    assert IBAN.is_valid("DE89 3704 0044 0532 0130 00")
    assert IBAN.is_valid("DE89370400440532013000")
    assert IBAN.is_valid("DE89 3704 0044 0532 0130 00")
    assert not IBAN.is_valid("DE89 3704 0044 0532 0130 0")
    assert not IBAN.is_valid("DE89 3704 0044 0532 0130 0")
    assert not IBAN.is_valid("DE89 3704 0044 0532 0130 0")
    assert not IBAN.is_valid("DE89 3704 0044 0532 0130 0")
    assert not IBAN.is_valid("DE89 3704 0044 0532 0130 0")
    assert not IBAN.is_valid("DE89 3704 0044 0532 0130 0")
    assert not IBAN.is_valid("")
    assert IBAN.format("de89370400440532013000") == "DE89 3704 0044 0532 0130 00"


def test_figi():
    assert FIGI.is_valid("BBG000B9XRY4")
    assert FIGI.is_valid("BBG000B9XRY4")
    assert not FIGI.is_valid("BBG000B9XRY")
    assert not FIGI.is_valid("BBG000B9XRY44")
    assert not FIGI.is_valid("")
    assert FIGI.format("bbg000b9xry4") == "BBG000B9XRY4"


def test_bic():
    assert BIC.is_valid("DEUTDEFF")
    assert not BIC.is_valid("DEUT22FF")
    assert not BIC.is_valid("DEUTDE")
    assert not BIC.is_valid("DEUTDEFF1")
    assert not BIC.is_valid("")
    assert BIC.format("deutdeff") == "DEUTDEFF"
    assert BIC.normalize("deutdeff") == "DEUTDEFF"
    assert BIC.normalize("ARMJAM22") == "ARMJAM22"
    assert BIC.normalize("ARMJAM22XXX") == "ARMJAM22"


def test_inn():
    assert INN.is_valid("7707083893")
    assert not INN.is_valid("770708389")
    assert not INN.is_valid("77070838933")
    assert not INN.is_valid("")
    assert INN.format("7707083893") == "7707083893"
    assert INN.normalize("7707083893") == "7707083893"
    assert INN.normalize("770708389") is None
    assert INN.normalize("") is None
    assert INN.format("7707083893") == "7707083893"


def test_lei():
    assert LEI.is_valid("1595VL9OPPQ5THEK2X30")
    assert not LEI.is_valid("1595VL9OPPQ5THEK2X")
    assert not LEI.is_valid("1595VL9OPPQ5THAK2X30")
    assert not LEI.is_valid("")
    assert LEI.format("1595vl9OPPQ5THEK2X30") == "1595VL9OPPQ5THEK2X30"
    assert LEI.normalize("1595VL9OPPQ5THEK2X30") == "1595VL9OPPQ5THEK2X30"
    assert LEI.normalize("1595VL9OPPQ5THEK") is None
    assert LEI.normalize("") is None


def test_cpf():
    assert CPF.is_valid("04485847608")
    assert not CPF.is_valid("334")
    assert not CPF.is_valid("33467854")
    assert not CPF.is_valid("")
    assert CPF.format("33467854390") == "334.678.543-90"
    assert CPF.normalize("04485847608") == "04485847608"
    assert CPF.normalize("044.858.476-08") == '04485847608'
    assert CPF.normalize("1114447773") is None
    assert CPF.normalize("") is None

def test_cnpj():
    assert CNPJ.is_valid("00000000000191")
    assert not CNPJ.is_valid("0000000000191")
    assert not CNPJ.is_valid("111447355")
    assert not CNPJ.is_valid("")
    assert CNPJ.format("00000000000191") == "00.000.000/0001-91"
    assert CNPJ.normalize("00000000000191") == "00000000000191"
    assert CNPJ.normalize("00.000.000/0001-91") == "00000000000191"
    assert CNPJ.normalize("0000000000019") is None
    assert CNPJ.normalize("") is None