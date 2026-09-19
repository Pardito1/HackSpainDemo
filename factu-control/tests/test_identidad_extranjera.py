"""Identidad fiscal e importes del lote 2, sobre las líneas literales de los PDF.

El maestro nuevo trae proveedores de Francia, Alemania, Japón y Brasil: sus NIF
e IBAN no tienen forma española y sus etiquetas están en otro idioma. Todo lo
que se lee aquí es determinista; el modelo no interviene.
"""

import pytest

from factu.extract import parse_fields
from test_fechas_letras import text_line


def field(*lineas):
    return parse_fields([text_line(l) for l in lineas])


@pytest.mark.parametrize("printed,expected", [
    ("IBAN: FR76 3000 6000 0112 3456 7890 189", "FR7630006000011234567890189"),
    ("IBAN: DE89 3704 0044 0532 0130 00", "DE89370400440532013000"),
    ("IBAN: JP01 0001 2331 2345 6789 012", "JP010001233123456789012"),
    ("IBAN: GB29 NWBK 6016 1331 9268 19", "GB29NWBK60161331926819"),
    ("IBAN: BR97 0036 0305 0000 1000 9795 493C1", "BR9700360305000010009795493C1"),
    ("Cuenta de abono (IBAN): ES14 0049 6170 6821 0004 3399",
     "ES1400496170682100043399"),
])
def test_iban_of_any_country_is_read_under_its_label(printed, expected):
    iban = field(printed)["iban"]
    assert iban["status"] == "OK" and iban["value"] == expected


def test_an_iban_without_its_label_is_not_a_candidate():
    assert field("Referencia interna: DE89 3704 0044 0532 0130 00")["iban"]["status"] == "MISSING"


def test_the_iban_does_not_swallow_the_words_that_follow_it():
    iban = field("IBAN: ES21 0049 1500 0512 3456 7890 TOTAL 121,00")["iban"]
    assert iban["value"] == "ES2100491500051234567890"


@pytest.mark.parametrize("printed,expected", [
    ("N° TVA: FR40303265045", "FR40303265045"),
    ("USt-ID: DE812345678", "DE812345678"),
    ("NIF: 5010401075570", "5010401075570"),
    ("NIF: 12.345.678/0001-95", "12.345.678/0001-95"),
    ("P. IVA: A46990201", "A46990201"),
])
def test_foreign_tax_ids_are_read_under_their_label(printed, expected):
    nif = field(printed)["supplier_nif"]
    assert nif["status"] == "OK" and nif["value"] == expected


@pytest.mark.parametrize("cliente", [
    "Client: Banco Miralmar S.A.  ·  CIF: A58231074",
    "Faturar a: Banco Miralmar S.A.  ·  NIF: A58231074",
    "Facturé à: Banco Miralmar S.A.  ·  N° TVA: A58231074",
    "Rechnungsempfänger: Banco Miralmar S.A.  ·  USt-ID: A58231074",
    "Bill to: Banco Miralmar S.A.  ·  Tax ID: A58231074",
])
def test_the_client_line_never_becomes_a_second_supplier_nif(cliente):
    nif = field("USt-ID: DE812345678", cliente)["supplier_nif"]
    assert nif["status"] == "OK" and nif["value"] == "DE812345678"


@pytest.mark.parametrize("printed,campo,expected", [
    ("Sous-total: € 1.560,00", "base", "1560.00"),
    ("Zwischensumme: € 3.120,00", "base", "3120.00"),
    ("Imponibile: € 2.340,00", "base", "2340.00"),
    ("Valor base: € 920,00", "base", "920.00"),
    ("Base imposable: € 1.180,00", "base", "1180.00"),
    ("GESAMT: € 3.775,20 EUR", "total", "3775.20"),
    ("TOTALE: € 2.831,40 EUR", "total", "2831.40"),
    ("TVA (21%): € 327,60", "tax_amount", "327.60"),
    ("MwSt. (21%): € 655,20", "tax_amount", "655.20"),
])
def test_amount_labels_of_the_batch(printed, campo, expected):
    amount = field(printed)[campo]
    assert amount["status"] == "OK" and amount["value"] == expected


def test_the_tva_of_a_tax_id_line_is_not_an_amount():
    # "N° TVA: FR40303265045" lleva la etiqueta en medio de la línea: no abre
    # un importe, y el número del NIF no puede colarse como cuota.
    fields = field("N° TVA: FR40303265045")
    assert fields["tax_amount"]["status"] == "MISSING"
    assert fields["supplier_nif"]["value"] == "FR40303265045"


def test_a_yen_amount_without_printed_cents_stays_missing():
    # "¥ 773,000" es ambiguo entre 773,00 y 773000: no se reconstruye.
    assert field("Base imponible: ¥ 773,000")["base"]["status"] == "MISSING"
