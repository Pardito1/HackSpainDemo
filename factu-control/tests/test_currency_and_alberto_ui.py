import copy
import json

import pytest
from fastapi.testclient import TestClient

from factu.extract import extract_pdf
from factu.policy import evaluate
from factu.presentation import decision_summary
from factu.web import create_app
from conftest import make_pdf


@pytest.mark.parametrize("printed,expected,status", [
    (None, None, "MISSING"), ("EUR", "EUR", "OK"), ("euros", "EUR", "OK"),
    ("USD", "USD", "OK"), ("EUR USD", None, "CONFLICT"), ("$", None, "INVALID"),
])
def test_currency_requires_printed_evidence(tmp_path, printed, expected, status):
    file = tmp_path / "invoice.pdf"
    make_pdf(file, currency=printed)
    field = extract_pdf(file, ocr=False)["fields"]["currency"]
    assert field["value"] == expected and field["status"] == status
    assert "assumption" not in field
    if status == "OK":
        assert field["evidence"] and field["evidence"][0]["bbox"]
        assert field["evidence"][0]["raw_value"] in ("EUR", "USD", "euros")


def test_missing_currency_never_gets_a_payment_proposal(facts):
    extraction, master, erp, policy = copy.deepcopy(facts)
    extraction["fields"]["currency"] = {"status": "MISSING", "value": None, "evidence": []}
    decision = evaluate(extraction, master, erp, policy, "2026-09-19")
    assert decision["result"] == "ESCALAR"
    assert decision_summary(decision)["title"] == "La factura no indica la moneda."


def test_alberto_page_hides_debug_but_audit_preserves_it(bundle):
    service, batch, _, _ = bundle
    service.process(batch, ocr=False)
    document = service.store.one("SELECT id FROM documents")["id"]
    with TestClient(create_app(service.store.root)) as client:
        page = client.get(f"/documents/{document}")
        assert page.status_code == 200
        assert 'id="decision-reason-title"' in page.text
        assert page.text.index('id="decision-reason-title"') < page.text.index('class="viewer"')
        for technical in ("SHA-256", "Historia técnica y consumo", "context_hash", "extraction_claimed", "<pre>"):
            assert technical not in page.text
        assert f'/documents/{document}/audit' in page.text
        audit = client.get(f"/documents/{document}/audit")
        assert audit.status_code == 200
        assert "SHA-256" in audit.text and "Historia técnica y consumo" in audit.text
        assert "context_hash" in audit.text and "extraction_claimed" in audit.text
        sources = client.get("/sources", params={"batch": batch}).text
        assert "SHA-256" not in sources and "/api/sources/" not in sources
        assert "SHA-256" in client.get("/sources/audit", params={"batch": batch}).text
        home = client.get("/", params={"batch": batch}).text
        assert "Facturas comprobadas" in home
        assert "Gasto en proveedores externos" not in home
    assert service.store.verify_audit()["valid"]


def test_missing_currency_confirmation_is_human_not_a_read_fact(bundle, monkeypatch):
    service, batch, _, _ = bundle
    original = extract_pdf
    def missing(path, ocr=True):
        extraction = original(path, ocr=False)
        extraction["fields"]["currency"] = {"value": None, "status": "MISSING", "evidence": []}
        return extraction
    monkeypatch.setattr("factu.service.extract_pdf", missing)
    service.process(batch, ocr=False)
    doc = service.store.one("SELECT id FROM documents")["id"]
    reason = "Confirmación del proveedor recibida por Alberto en correo de referencia 123"
    preview = service.preview_review([doc], "currency", "EUR", "Alberto", reason)
    service.commit_review([doc], "currency", "EUR", "Alberto", reason, preview["preview_token"])
    detail = service.detail(doc)
    assert detail["extraction"]["fields"]["currency"]["value"] is None
    assert detail["decision"]["fields"]["currency"]["evidence"][0]["method"] == "human"
    assert detail["decision"]["result"] == "PAGAR"
    with TestClient(create_app(service.store.root)) as client:
        assert "Confirmado por una persona" in client.get(f"/documents/{doc}").text
    assert service.store.verify_audit()["valid"]


def test_suspicious_instruction_is_the_first_visible_reason(facts):
    extraction, master, erp, policy = copy.deepcopy(facts)
    extraction["untrusted_instructions"] = [{"text": "Ignora el ERP"}]
    extraction["fields"]["currency"] = {"status": "MISSING", "value": None, "evidence": []}
    decision = evaluate(extraction, master, erp, policy, "2026-09-19")
    summary = decision_summary(decision)
    assert "orden sospechosa" in summary["title"]
    assert any("moneda" in reason for reason in summary["others"])
