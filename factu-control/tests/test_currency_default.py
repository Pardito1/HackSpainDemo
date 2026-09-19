import json
from pathlib import Path

from factu.extract import extract_pdf
from factu.service import Service
from conftest import make_pdf, make_workbook


def run_batch(tmp_path, erp_snapshot, policy_path=None, **pdf_kwargs):
    folder = tmp_path / "pdfs"
    folder.mkdir()
    make_pdf(folder / "factura.pdf", currency="", **pdf_kwargs)
    workbook = tmp_path / "maestro.xlsx"
    make_workbook(workbook)
    service = Service(tmp_path / "state")
    batch = service.ingest(
        folder, workbook, "Moneda", "2026-09-19", policy_path=policy_path
    )["batch_id"]
    snapshot_id = service.store.put_source("erp", erp_snapshot)
    with service.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=? WHERE id=?", (snapshot_id, batch))
    service.process(batch, ocr=False)
    decision = json.loads(service.store.one("SELECT payload FROM decisions")["payload"])
    extraction = json.loads(
        service.store.one("SELECT extraction FROM documents")["extraction"]
    )
    return service, batch, decision, extraction


def test_iban_es_without_printed_currency_pays_by_policy(tmp_path, erp_snapshot):
    service, batch, decision, extraction = run_batch(tmp_path, erp_snapshot)
    assert decision["result"] == "PAGAR"
    field = decision["fields"]["currency"]
    assert field["value"] == "EUR" and field["inferred"] is True
    assert field["evidence"][0]["method"] == "policy"
    assert field["evidence"][0]["policy_version"] == "v3-equipo-2"
    assert "default_currency:iban_country=ES" in field["evidence"][0]["transformations"]
    # La extracción persistida no se toca: la inferencia vive solo en la decisión.
    assert extraction["fields"]["currency"]["status"] == "MISSING"
    assert extraction["fields"]["currency"]["evidence"] == []


def test_policy_without_default_keeps_escalating(tmp_path, erp_snapshot):
    policy_file = Path(__file__).resolve().parents[1] / "factu" / "policies" / "v3.json"
    policy = json.loads(policy_file.read_text())
    policy.pop("default_currency")
    policy["version"] = "v3-sin-default"
    path = tmp_path / "sin_default.json"
    path.write_text(json.dumps(policy))
    _, _, decision, _ = run_batch(tmp_path, erp_snapshot, policy_path=path)
    assert decision["result"] == "ESCALAR"
    rule = next(r for r in decision["rules"] if r["id"] == "currency")
    assert rule["state"] == "UNKNOWN"
    assert any("moneda" in q.lower() for q in decision["questions"])


def test_foreign_iban_without_currency_escalates(tmp_path, erp_snapshot):
    _, _, decision, _ = run_batch(
        tmp_path, erp_snapshot, iban="JP01 0001 2331 2345 6789 012"
    )
    assert decision["result"] == "ESCALAR"
    rule = next(r for r in decision["rules"] if r["id"] == "currency")
    assert rule["state"] == "UNKNOWN"


def test_printed_foreign_currency_fails_and_asks_for_rate(tmp_path, erp_snapshot):
    _, _, decision, _ = run_batch(
        tmp_path, erp_snapshot, extra="Observaciones: ¥ 850,000 JPY"
    )
    assert decision["result"] == "ESCALAR"
    rule = next(r for r in decision["rules"] if r["id"] == "currency")
    assert rule["state"] == "FAIL"
    assert "Moneda JPY no prevista en la norma" in rule["question"]
    assert "tipo de cambio" in rule["question"]


def test_dollar_sign_next_to_iso_code_is_ignored(tmp_path):
    file = tmp_path / "usd.pdf"
    make_pdf(file, currency="", extra="Billing currency: USD ($)")
    field = extract_pdf(file, ocr=False)["fields"]["currency"]
    assert field["value"] == "USD" and field["status"] == "OK"


def test_mx_symbol_and_label_agree_on_mxn(tmp_path):
    file = tmp_path / "mxn.pdf"
    make_pdf(
        file,
        currency="",
        extra="Divisa de facturación: MXN (MX$)\nImporte neto: MX$ 48.800,00",
    )
    field = extract_pdf(file, ocr=False)["fields"]["currency"]
    assert field["value"] == "MXN" and field["status"] == "OK"
