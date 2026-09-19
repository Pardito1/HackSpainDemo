from pathlib import Path

import pytest

import scripts.evaluate_lote2_ocr as evaluator
from scripts.evaluate_lote2_ocr import EvaluationError, PROFILE, evaluate


FIELDS = {
    "invoice_number": "INV-001",
    "supplier_nif": "B12345674",
    "iban": "ES9121000418450200051332",
    "order": "PO-2026-0001",
    "date": "2026-02-01",
    "base": "100.00",
    "tax_rate": "21",
    "tax_amount": "21.00",
    "total": "121.00",
    "currency": "EUR",
}


def labels_for(names):
    return {
        "documents": {
            name: {
                "template_id": "template-" + name,
                "supplier_id": "supplier-" + name,
                "fields": {field: {"value": value} for field, value in FIELDS.items()},
            }
            for name in names
        }
    }


def extraction(currency="EUR"):
    values = FIELDS | {"currency": currency}
    return {
        "profile": PROFILE,
        "version": "lote2-ocr-test-v1",
        "fields": {
            key: {"status": "OK", "value": value}
            for key, value in values.items()
        },
        "pages": [{"method": "lote2_ocr_v1"}],
        "warnings": [],
        "untrusted_instructions": [],
    }


def test_evaluator_uses_lote2_profile_and_reports_safe_coverage(tmp_path):
    names = ["train.pdf", "validation.pdf", "test.pdf"]
    for name in names:
        (tmp_path / name).write_bytes(b"not parsed by fake extractor")
    calls = []

    def fake_extractor(path, *, ocr, profile):
        calls.append((Path(path).name, ocr, profile))
        return extraction("USD" if Path(path).name == "test.pdf" else "EUR")

    report = evaluate(
        tmp_path,
        labels_for(names),
        {"splits": {"train": ["train.pdf"], "validation": ["validation.pdf"], "test": ["test.pdf"]}},
        extractor=fake_extractor,
        strict_groups=True,
    )

    assert PROFILE == "lote2_ocr_v1"
    assert calls == [
        ("test.pdf", True, "lote2_ocr_v1"),
        ("train.pdf", True, "lote2_ocr_v1"),
        ("validation.pdf", True, "lote2_ocr_v1"),
    ]
    currency = report["overall"]["field_metrics"]["currency"]
    assert currency["exact_match_accuracy"] == pytest.approx(2 / 3)
    assert currency["autoaccept_precision"] == pytest.approx(2 / 3)
    assert currency["autoaccept_coverage"] == 1
    # La factura del test se autoaceptaría según sus estados, pero el informe
    # deja visible que sería una autoaceptación insegura por moneda incorrecta.
    assert report["splits"]["test"]["document_autoaccept_precision"] == 0
    assert report["splits"]["test"]["document_autoaccept_safe_coverage"] == 0
    assert report["protocol"]["evaluation_split_role"].startswith("train/validation/test")
    assert "test_is_reserved" not in report["protocol"]
    assert report["provenance"]["profile_identity"]["profile"] == PROFILE
    assert set(report["provenance"]["pdf_sha256"]) == set(names)
    assert any(e["file_id"] == "test.pdf" and e["field"] == "currency" for e in report["errors"])


def test_default_extractor_path_passes_the_requested_profile(tmp_path, monkeypatch):
    names = ["train.pdf", "validation.pdf", "test.pdf"]
    for name in names:
        (tmp_path / name).write_bytes(b"fixture")
    calls = []

    def fake_extract_pdf(path, *, ocr, profile):
        calls.append((Path(path).name, ocr, profile))
        return extraction()

    monkeypatch.setattr(evaluator, "extract_pdf", fake_extract_pdf)
    evaluate(
        tmp_path,
        labels_for(names),
        {"splits": {"train": ["train.pdf"], "validation": ["validation.pdf"], "test": ["test.pdf"]}},
    )
    assert all(profile == "lote2_ocr_v1" for _, _, profile in calls)


def test_evaluator_refuses_accuracy_without_manual_labels(tmp_path):
    with pytest.raises(EvaluationError, match="No hay etiquetas manuales"):
        evaluate(
            tmp_path,
            {"documents": {}},
            {"splits": {"train": ["train.pdf"], "validation": ["validation.pdf"], "test": ["test.pdf"]}},
            extractor=lambda path, *, ocr, profile: extraction(),
        )


def test_missing_field_can_be_exact_without_becoming_autoaccepted(tmp_path):
    """A correct absence must not make autoaccept precision exceed one."""
    names = ["train.pdf", "validation.pdf", "test.pdf"]
    for name in names:
        (tmp_path / name).write_bytes(b"fixture")
    labels = labels_for(names)
    for record in labels["documents"].values():
        record["fields"]["currency"] = {"value": None}

    def missing_currency(path, *, ocr, profile):
        result = extraction()
        result["fields"]["currency"] = {"status": "MISSING", "value": None}
        return result

    report = evaluate(
        tmp_path,
        labels,
        {"splits": {"train": ["train.pdf"], "validation": ["validation.pdf"], "test": ["test.pdf"]}},
        extractor=missing_currency,
    )
    currency = report["overall"]["field_metrics"]["currency"]
    assert currency["exact_match_accuracy"] == 1
    assert currency["autoaccepted"] == 0
    assert currency["autoaccept_precision"] is None
    assert currency["autoaccept_safe_coverage"] == 0


def test_evaluator_rejects_split_leakage(tmp_path):
    (tmp_path / "same.pdf").write_bytes(b"fixture")
    with pytest.raises(EvaluationError, match="Fuga entre splits"):
        evaluate(
            tmp_path,
            labels_for(["same.pdf"]),
            {"splits": {"train": ["same.pdf"], "validation": ["same.pdf"], "test": ["same.pdf"]}},
            extractor=lambda path, *, ocr, profile: extraction(),
        )
