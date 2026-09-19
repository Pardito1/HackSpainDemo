import pytest

from factu.extract import parse_fields
from factu.service import Service
from factu.utils import date_language, invoice_date
from conftest import make_pdf, make_workbook


def text_line(text):
    return {"text": text, "raw_text": text, "words": [], "bbox": [0, 0, 100, 10],
            "page": 1, "method": "native"}


@pytest.mark.parametrize("printed,expected,language", [
    ("dos de enero de dos mil veintiséis", "2026-01-02", "es"),
    ("the seventh of March, two thousand twenty-six", "2026-03-07", "en"),
    ("03 Feb 2026", "2026-02-03", "en"),
    ("dos de gener de dos mil vint-i-sis", "2026-01-02", "ca"),
    ("15 de fevereiro de 2026", "2026-02-15", "pt"),
    ("le trois janvier deux mille vingt-six", "2026-01-03", "fr"),
    ("sette agosto duemilaventisei", "2026-08-07", "it"),
    ("am siebten März zweitausendsechsundzwanzig", "2026-03-07", "de"),
    ("am fünfzehnten Juni zweitausendsechsundzwanzig", "2026-06-15", "de"),
])
def test_dates_in_words_across_seven_languages(printed, expected, language):
    assert invoice_date(printed) == expected
    assert date_language(printed) == language


def test_numeric_date_is_not_reported_as_words():
    assert invoice_date("30/05/2026") == "2026-05-30"
    assert date_language("30/05/2026") is None


def test_impossible_date_in_words_is_invalid():
    with pytest.raises(ValueError):
        invoice_date("31 de febrero de 2026")


def test_portuguese_label_and_numeric_value_are_read():
    field = parse_fields([text_line("Data de emissão: 30/05/2026")])["date"]
    assert field["value"] == "2026-05-30" and field["status"] == "OK"


def test_words_candidate_records_the_table_it_came_from():
    field = parse_fields(
        [text_line("Fecha de emisión: dos de enero de dos mil veintiséis")]
    )["date"]
    assert field["value"] == "2026-01-02"
    assert "date_words:es" in field["evidence"][0]["transformations"]
    assert field["evidence"][0]["raw_value"] == "dos de enero de dos mil veintiséis"


@pytest.mark.parametrize("printed", [
    "__________________________ 15 de ma rz o d e 2 0 2 6",
    "Condiciones de pago: 30 dias desde la fecha de emision.",
])
def test_broken_and_prose_lines_produce_no_date_candidate(printed):
    field = parse_fields([text_line(printed)])["date"]
    assert field["status"] == "MISSING" and field["evidence"] == []


def test_ingest_rejects_an_as_of_before_the_last_order(tmp_path):
    folder = tmp_path / "pdfs"
    folder.mkdir()
    make_pdf(folder / "factura.pdf")
    workbook = tmp_path / "maestro.xlsx"
    make_workbook(workbook)
    service = Service(tmp_path / "state")
    with pytest.raises(ValueError, match="anterior al último pedido del maestro"):
        service.ingest(folder, workbook, "Fecha mal", "2026-01-19")
    assert service.store.all("SELECT * FROM batches") == []
