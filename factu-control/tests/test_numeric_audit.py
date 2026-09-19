"""Numeric regression cases: never borrow a different field's plausible amount."""
from decimal import Decimal
import pytest
from factu.extract import parse_fields
from factu.policy import evaluate
from factu.presentation import euros


def parse(text):
    return parse_fields([{"text": text, "raw_text": text, "page": 1,
                         "method": "test", "bbox": [0, 0, 300, 20], "words": []}])


@pytest.mark.parametrize("text,base,tax,total", [
    ("Base 433,87 IVA21%91,11 TOTAL524,98EUR", "433.87", "91.11", "524.98"),
    ("Base1.025,49IVA21%215,35TOTAL1.240,84EUR", "1025.49", "215.35", "1240.84"),
    ("Base 1 234,56 IVA (21%): 259,26 TOTAL 1 493,82 EUR", "1234.56", "259.26", "1493.82"),
    ("Base221,55 1VA21%46.53 TOTAL268,08EUR", "221.55", "46.53", "268.08"),
])
def test_joined_labels_and_grouped_thousands(text, base, tax, total):
    fields = parse(text)
    assert fields["base"]["value"] == base
    assert fields["tax_amount"]["value"] == tax
    assert fields["total"]["value"] == total
    assert fields["tax_rate"]["value"] == "21"
    assert fields["currency"]["value"] == "EUR"


def test_corrupted_base_is_not_replaced_by_tax():
    fields = parse("Base 1.292.88 IVA21%271,50")
    assert fields["base"]["status"] == "INVALID"
    assert fields["base"]["value"] is None
    assert fields["tax_amount"]["value"] == "271.50"


def test_rate_alone_is_not_a_tax_amount():
    fields = parse("IVA 21,00%")
    assert fields["tax_amount"]["status"] == "MISSING"
    assert fields["tax_rate"]["value"] == "21.00"


@pytest.mark.parametrize("text", ["TOTAL (121,00)", "TOTAL −121,00", "TOTAL - 121,00"])
def test_explicit_negative_preserved(text):
    assert parse(text)["total"]["value"] == "-121.00"


def test_multiple_amounts_not_silently_last_wins():
    assert parse("TOTAL 121,00 EUR / 100,00 USD")["total"]["status"] == "CONFLICT"


def test_missing_decimal_separator_is_not_invented():
    assert parse("TOTAL 12100 EUR")["total"]["status"] == "MISSING"


def test_damaged_number_cannot_be_skipped_to_borrow_later_amount():
    assert parse("Base 22155 texto ilegible 46,53")["base"]["value"] is None


@pytest.mark.parametrize("base,rate,tax,total,expected", [
    ("0.50", "21", "0.11", "0.61", "PASS"),
    ("0.50", "21", "0.12", "0.62", "PASS"),
    ("0.50", "21", "0.13", "0.63", "FAIL"),
    ("100", "0", "0.00", "100.00", "PASS"),
])
def test_half_up_and_cent_tolerance(facts, base, rate, tax, total, expected):
    for key, value in [("base",base),("tax_rate",rate),("tax_amount",tax),("total",total)]:
        facts[0]["fields"][key]["value"] = value
    result = evaluate(*facts, "2026-09-19")
    assert next(r for r in result["rules"] if r["id"]=="tax_arithmetic")["state"] == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_display_is_not_a_valid_amount(value):
    assert euros(value) == "Por confirmar"


def test_p95_nearest_rank(bundle):
    service, batch, *_ = bundle
    for i in range(1, 21):
        service.store.cost("extract", i, batch_id=batch)
    assert service.dashboard(batch)["metrics"]["extract_p95"] == 19
