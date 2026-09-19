"""Contrato del perfil OCR aislado para el lote 2.

No comprueba decisiones: esas siguen siendo responsabilidad de policy.py.
Aquí solo se fija que la lectura multilingüe conserve evidencia y no deduzca
moneda a partir de una factura española.
"""

from pathlib import Path

import pymupdf as fitz
import pytest

from factu.extract import extract_pdf
from factu.lote2_ocr import (
    PROFILE,
    _annotation_risks,
    _mark_struck_amounts,
    cache_identity,
    group_lines,
    merge_native_and_ocr,
    parse_lote2_fields,
)


def _lines(text, method="pymupdf", confidence=None):
    tokens = [
        {"text": line, "bbox": [20, 20 + n * 18, 520, 33 + n * 18], "confidence": confidence}
        for n, line in enumerate(text.splitlines())
    ]
    return group_lines(tokens, 1, method)


def _field(value, status="OK", confidence=0.99):
    evidence = [] if value is None else [{"value": value, "confidence": confidence, "method": "rapidocr-lote2"}]
    return {"value": value if status == "OK" else None, "status": status, "evidence": evidence}


def test_lote2_parser_reads_explicit_jpy_and_international_identifiers():
    fields = parse_lote2_fields(_lines("""Tokyo Systems K.K.
NIF: 5010401075570
IBAN: JP01 0001 2331 2345 6789 012
FACTURA Nº: INV-9109
Fecha de emisión: 12/04/2026
Ref. Pedido: PO-2026-1309
Divisa de facturación: JPY (¥)
Base imponible: ¥ 773,000
IVA (21%): ¥ 77,000
TOTAL: ¥ 850,000 JPY"""))
    assert fields["supplier_nif"]["value"] == "5010401075570"
    assert fields["iban"]["value"] == "JP010001233123456789012"
    assert fields["order"]["value"] == "PO-2026-1309"
    assert fields["currency"]["value"] == "JPY"
    assert fields["total"]["value"] == "850000"


@pytest.mark.parametrize("currency_line", ["", "Servicio: $ 100,00", "Servicio: ¥ 773,000"])
def test_lote2_parser_never_assumes_eur_from_spanish_context(currency_line):
    fields = parse_lote2_fields(_lines("\n".join(part for part in [
        "FACTURA Nº: FA-1650", "NIF: B98455101", "IBAN: ES27 0239 0806 6671 2233 4455",
        "Fecha: 22/08/2026", "Pedido: PO-2026-0071", "Base: 786,69", "IVA (21%): 165,20",
        "TOTAL: 951,89", currency_line,
    ] if part)))
    assert fields["currency"]["value"] is None
    assert fields["currency"]["status"] in {"MISSING", "INVALID"}


def test_lote2_parser_preserves_conflicting_printed_tax_rates():
    fields = parse_lote2_fields(_lines("""Billing currency: USD ($) - per framework agreement (0% export VAT).
VAT (21%): $ 0.00
TOTAL: $ 2,450.00 USD"""))
    assert fields["currency"]["value"] == "USD"
    assert fields["tax_rate"]["status"] == "CONFLICT"
    assert {item["value"] for item in fields["tax_rate"]["evidence"] if item["value"]} == {"0", "21"}


def test_weak_ocr_witness_cannot_replace_valid_native_value():
    native = {field: _field(None, "MISSING") for field in (
        "invoice_number", "supplier_nif", "iban", "order", "date", "base", "tax_rate", "tax_amount", "total", "currency"
    )}
    native["total"] = _field("121.00")
    witness = {field: _field(None, "MISSING") for field in native}
    witness["total"] = _field("999.00", confidence=0.60)
    warnings = []
    merged = merge_native_and_ocr(native, witness, warnings)
    assert merged["total"]["status"] == "OK"
    assert merged["total"]["value"] == "121.00"
    assert warnings[0]["code"] == "OCR_WITNESS_WEAK_CONFLICT"


def test_annotation_risks_flag_fragmented_or_corrected_text():
    line = _lines("IVA (21%): 315,00 € co r r e g i d o A . ")[0]
    risks = _annotation_risks([line], [{"number": 1, "fragment_ratio": 0.7, "native_length": 140}])
    assert {risk["reason"] for risk in risks} == {"TEXT_FRAGMENTATION", "POSSIBLE_MANUAL_CORRECTION"}


def test_colored_stroke_over_amount_preserves_conflict_instead_of_correcting():
    fields = {field: _field(None, "MISSING") for field in (
        "invoice_number", "supplier_nif", "iban", "order", "date", "base", "tax_rate", "tax_amount", "total", "currency"
    )}
    fields["base"] = {
        "value": "1500.00", "status": "OK",
        "evidence": [{"value": "1500.00", "page": 1, "bbox": [120, 240, 165, 255]}],
    }
    risks = []
    _mark_struck_amounts(fields, [{"number": 1, "_colored_strokes": [{"bbox": [154, 240, 235, 250]}]}], risks)
    assert fields["base"]["status"] == "CONFLICT"
    assert fields["base"]["value"] is None
    assert risks[0]["reason"] == "STRUCK_OUT_AMOUNT"


def test_lote2_profile_marks_rapidocr_evidence_without_changing_standard(tmp_path, monkeypatch):
    path = Path(tmp_path) / "factura.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 40), "FACTURA Nº: FA-1001\nNIF: B12345674\nTOTAL: 121,00 EUR")
    doc.save(path)
    doc.close()

    monkeypatch.setenv("FACTU_LOTE2_OCR_MODE", "always")
    monkeypatch.setattr(
        "factu.extract.ocr_page",
        lambda page: [
            {"text": "FACTURA Nº: FA-1001", "bbox": [40, 40, 240, 55], "confidence": 0.99},
            {"text": "NIF: B12345674", "bbox": [40, 60, 220, 75], "confidence": 0.99},
            {"text": "TOTAL: 121,00 EUR", "bbox": [40, 80, 240, 95], "confidence": 0.99},
        ],
    )
    lote2 = extract_pdf(path, profile=PROFILE)
    standard = extract_pdf(path, ocr=False)
    assert lote2["profile"] == PROFILE
    assert lote2["ocr_metadata"]["pages_run"] == [1]
    assert any(item["method"] == "rapidocr-lote2" for item in lote2["fields"]["total"]["evidence"])
    assert lote2["pages"][0]["witness_evidence"][0]["method"] == "rapidocr-lote2"
    assert lote2["pages"][0]["witness_evidence"][0]["bbox"]
    assert "profile" not in standard


def test_lote2_keeps_native_result_and_reports_missing_ocr_runtime(tmp_path, monkeypatch):
    path = Path(tmp_path) / "needs-witness.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 40), "FACTURA Nº: FA-1002\nNIF: B12345674\nTOTAL: 121,00 EUR")
    doc.save(path)
    doc.close()

    def unavailable(_page):
        raise RuntimeError("OCR no instalado: pip install '.[ocr]'")

    monkeypatch.setattr("factu.extract.ocr_page", unavailable)
    result = extract_pdf(path, profile=PROFILE)
    assert result["fields"]["invoice_number"]["value"] == "FA-1002"
    assert result["ocr_metadata"]["pages_requested"] == [1]
    assert result["ocr_metadata"]["pages_run"] == []
    assert any(warning["code"] == "OCR_UNAVAILABLE" for warning in result["warnings"])


def test_lote2_cache_identity_seals_profile_version_mode_and_thresholds(monkeypatch):
    monkeypatch.setenv("FACTU_LOTE2_OCR_MODE", "always")
    identity = cache_identity()
    assert identity["profile"] == PROFILE
    assert identity["version"]
    assert identity["mode"] == "always"
    assert identity["min_witness_confidence"] > 0.5
    assert identity["min_conflict_confidence"] > identity["min_witness_confidence"]
