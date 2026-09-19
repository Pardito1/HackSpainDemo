import copy
import json

import pytest
from fastapi.testclient import TestClient

from factu.web import create_app
from conftest import make_pdf


def processed(bundle):
    service, batch, *_ = bundle
    service.process(batch, ocr=False)
    return service, batch, service.store.one("SELECT * FROM documents")


def answer(service, doc, result="ESCALAR", acknowledged=None):
    args = (doc["id"], result, "Alberto", "He comprobado las fuentes y solicito confirmación al responsable.",
            "Referencia de validación: expediente interno 27", acknowledged or [], 90)
    preview = service.human_preview(*args)
    return args, preview


def test_human_question_preserves_fact_and_result(bundle):
    service, batch, doc = processed(bundle)
    args, preview = answer(service, doc)
    service.human_commit(*args, preview["preview_token"])
    detail = service.detail(doc["id"])
    assert detail["document"]["extraction"] == doc["extraction"]
    assert detail["decision"]["engine_result"] == "PAGAR"
    assert detail["decision"]["result"] == "ESCALAR"
    assert detail["decision"]["human_decision"]["actor"] == "Alberto"
    assert len(detail["history"]) == 2
    assert service.dashboard(batch)["metrics"]["human_seconds"] == 90
    service.evaluate_batch(batch)
    assert service.export_rows(batch)[0]["result"] == "ESCALAR"
    assert service.store.verify_audit()["valid"]


def test_human_confirm_and_stale_preview(bundle):
    service, batch, doc = processed(bundle)
    args, preview = answer(service, doc, "NO_PAGAR")
    service.human_commit(*args, preview["preview_token"])
    assert service.export_rows(batch)[0]["result"] == "NO_PAGAR"
    with pytest.raises(ValueError, match="cambió"):
        service.human_commit(*args, preview["preview_token"])


def test_human_cannot_override_paid_or_bad_iban(bundle):
    service, batch, doc = processed(bundle)
    args = ([doc["id"]], "iban", "ES0000000000000000000000", "Ana", "Leído en el original de prueba")
    preview = service.preview_review(*args)
    service.commit_review(*args, preview["preview_token"])
    with pytest.raises(ValueError, match="No se puede"):
        answer(service, doc, "PAGAR")
    erp = copy.deepcopy(service.store.source(service.batch(batch)["snapshot_id"]))
    erp["rows"][0]["estado"] = "PAGADA"
    new_id = service.store.put_source("erp", erp)
    plan = service.preview_source(batch, "erp", new_id, "Ana", "Pago confirmado en ERP")
    service.commit_source(plan["id"])
    with pytest.raises(ValueError, match="No se puede"):
        answer(service, doc, "PAGAR")


def test_business_identity_conflict_can_be_resolved_with_explicit_evidence(bundle):
    service, batch, doc = processed(bundle)
    master = copy.deepcopy(service.store.source(service.batch(batch)["master_id"]))
    master["orders"]["PO-2026-0001"][0]["supplier_id"] = "P999"
    plan = service.preview_source(batch, "master", service.store.put_source("master", master), "Ana", "Nueva versión de prueba del maestro")
    service.commit_source(plan["id"])
    assert service.export_rows(batch)[0]["result"] == "ESCALAR"
    with pytest.raises(ValueError, match="expresamente"):
        answer(service, doc, "PAGAR")
    args, preview = answer(service, doc, "PAGAR", ["source_identity_conflict"])
    service.human_commit(*args, preview["preview_token"])
    assert service.export_rows(batch)[0]["result"] == "PAGAR"
    assert service.detail(doc["id"])["decision"]["engine_result"] == "ESCALAR"


def test_changed_fact_expires_human_response_and_reuses_ocr(bundle):
    service, batch, doc = processed(bundle)
    args, preview = answer(service, doc, "NO_PAGAR")
    service.human_commit(*args, preview["preview_token"])
    erp = copy.deepcopy(service.store.source(service.batch(batch)["snapshot_id"]))
    erp["rows"][0]["importe"] = "200.00"
    original = doc["extraction"]
    n = service.store.one("SELECT count(*) n FROM extraction_cache")["n"]
    plan = service.preview_source(batch, "erp", service.store.put_source("erp", erp), "Ana", "Asiento corregido por contabilidad")
    assert len(plan["affected"]) == 1 and plan["affected"][0]["human_response_stale"]
    service.commit_source(plan["id"])
    detail = service.detail(doc["id"])
    assert detail["decision"]["result"] == "ESCALAR"
    assert detail["decision"]["human_response_stale"]
    assert detail["document"]["extraction"] == original
    assert service.store.one("SELECT count(*) n FROM extraction_cache")["n"] == n


def test_unrelated_change_preserves_human_answer_and_decision(bundle):
    service, batch, doc = processed(bundle)
    args, preview = answer(service, doc, "NO_PAGAR")
    service.human_commit(*args, preview["preview_token"])
    before = service.document(doc["id"])["latest_decision"]
    erp = copy.deepcopy(service.store.source(service.batch(batch)["snapshot_id"]))
    erp["rows"].append(erp["rows"][0] | {"pedido":"PO-2026-9999", "id":"2"})
    erp["total"] = 2
    plan = service.preview_source(batch, "erp", service.store.put_source("erp", erp), "Ana", "Añadido asiento de otro proveedor")
    assert len(plan["reused"]) == 1 and not plan["affected"]
    service.commit_source(plan["id"])
    assert service.document(doc["id"])["latest_decision"] == before
    assert service.export_rows(batch)[0]["result"] == "NO_PAGAR"
    assert service.store.one("SELECT * FROM events WHERE kind='decision_reused'")
    service.evaluate_batch(batch)
    assert service.export_rows(batch)[0]["result"] == "NO_PAGAR"


def test_source_preview_stale_after_human_answer(bundle):
    service, batch, doc = processed(bundle)
    source_id = service.batch(batch)["snapshot_id"]
    plan = service.preview_source(batch, "erp", source_id, "Ana", "Comprobación antes de aplicar")
    args, preview = answer(service, doc)
    service.human_commit(*args, preview["preview_token"])
    with pytest.raises(ValueError, match="cambiado"):
        service.commit_source(plan["id"])


def test_master_norm_requires_explicit_ack(bundle):
    service, batch, doc = processed(bundle)
    master = copy.deepcopy(service.store.source(service.batch(batch)["master_id"]))
    master["rules"].append({"cell":"A2", "text":"Nueva condición de pago"})
    source_id = service.store.put_source("master", master)
    with pytest.raises(ValueError, match="norma"):
        service.preview_source(batch, "master", source_id, "Ana", "Cambio normativo de prueba")
    plan = service.preview_source(batch, "master", source_id, "Ana", "Revisada correspondencia con política", True)
    assert plan["rules_changed"] and len(plan["affected"]) == 1


def test_change_is_applied_only_once_and_audited(bundle):
    service, batch, doc = processed(bundle)
    erp = copy.deepcopy(service.store.source(service.batch(batch)["snapshot_id"]))
    erp["rows"][0]["estado"] = "PAGADA"
    source = service.store.put_source("erp", erp)
    plan = service.preview_source(batch, "erp", source, "Ana", "Pago confirmado por contabilidad")
    assert service.export_rows(batch)[0]["result"] == "PAGAR"  # Preview is not applied.
    assert plan["affected"][0]["after"] == "NO_PAGAR"
    service.commit_source(plan["id"])
    assert service.export_rows(batch)[0]["result"] == "NO_PAGAR"
    with pytest.raises(ValueError, match="pendiente"):
        service.commit_source(plan["id"])
    assert service.store.verify_audit()["valid"]


def test_new_routes_forms_and_injection_escaped(bundle):
    service, batch, doc = processed(bundle)
    app = create_app(service.store.root)
    with TestClient(app) as client:
        for path in ["/sources", "/sources?batch="+batch, "/?result=ESCALAR", "/?q=nothing", "/?page=900"]:
            assert client.get(path).status_code == 200
        assert client.get(f"/api/batches/{batch}/export?filename=outcomes_lote2.jsonl").headers["content-disposition"].endswith('"outcomes_lote2.jsonl"')
        assert client.get(f"/api/batches/{batch}/export?filename=../bad").status_code == 400
        args, preview = answer(service, doc)
        body = {"result":"ESCALAR","actor":"<script>alert(1)</script>", "reason":args[3], "evidence":args[4], "seconds":90,"acknowledged":[]}
        headers = {"X-CSRF-Token":app.state.service.store.csrf_token}
        assert client.post(f"/api/documents/{doc['id']}/answer/preview",json=body).status_code == 403
        response=client.post(f"/api/documents/{doc['id']}/answer/preview",json=body,headers=headers)
        assert response.status_code == 200
        body["preview_token"] = response.json()["preview_token"]
        assert client.post(f"/api/documents/{doc['id']}/answer/commit",json=body,headers=headers).status_code == 200
        html=client.get("/documents/"+doc["id"]).text
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


def test_selective_change_only_affected_document(bundle, tmp_path):
    service, batch, folder, workbook = bundle
    # Use a second independent invoice in the same lot, rather than duplicate obligations.
    second=folder/"second.pdf"
    make_pdf(second)
    import pymupdf as fitz
    with fitz.open(second) as pdf:
        for rect in pdf[0].search_for("PO-2026-0001"):
            pdf[0].add_redact_annot(rect)
        pdf[0].apply_redactions()
        pdf[0].insert_text((97,146),"PO-2026-0002",fontsize=12)
        pdf.save(tmp_path/"replacement.pdf")
    # Register both synthetic originals through ingestion, including their manifests.
    erp=copy.deepcopy(service.store.source(service.batch(batch)["snapshot_id"]))
    import shutil
    from factu.service import Service
    shutil.copyfile(tmp_path/"replacement.pdf", second)
    service=Service(tmp_path/"selective-state")
    batch=service.ingest(folder,workbook,"Selective","2026-09-19")["batch_id"]
    second_id=service.store.one("SELECT id FROM documents WHERE file_id='second.pdf'")["id"]
    erp["rows"].append(erp["rows"][0]|{"id":"2","pedido":"PO-2026-0002"})
    erp["total"]=2
    sid=service.store.put_source("erp",erp)
    with service.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=? WHERE id=?",(sid,batch))
    service.process(batch,ocr=False)
    previous=service.document(second_id)["latest_decision"]
    erp["rows"][0]["estado"]="PAGADA"
    plan=service.preview_source(batch,"erp",service.store.put_source("erp",erp),"Ana","Cambio de estado de un solo asiento")
    assert len(plan["affected"])==1 and len(plan["reused"])==1
    service.commit_source(plan["id"])
    assert service.document(second_id)["latest_decision"]==previous


def test_new_code_does_not_silently_discard_human_rejection(bundle):
    service, batch, doc = processed(bundle)
    args, preview = answer(service, doc, "NO_PAGAR")
    service.human_commit(*args, preview["preview_token"])
    service.code_sha256 = "new-reviewed-code"
    service.evaluate_batch(batch)
    decision = service.detail(doc["id"])["decision"]
    assert decision["engine_result"] == "PAGAR"
    assert decision["result"] == "ESCALAR" and decision["human_response_stale"]


def test_internal_human_question_does_not_become_supplier_email(bundle):
    service, batch, doc = processed(bundle)
    args, preview = answer(service, doc)
    service.human_commit(*args, preview["preview_token"])
    before = service.document(doc["id"])["latest_decision"]
    assert service.consultation_drafts(batch) == []
    app = create_app(service.store.root)
    with TestClient(app) as client:
        assert "No hay consultas externas" in client.get("/groups?batch=" + batch).text
        assert client.get("/api/consultations/not-found/draft").status_code == 404
    assert service.document(doc["id"])["latest_decision"] == before


def test_duplicate_human_anchor_matches_batch_evaluation(bundle):
    service, batch, folder, workbook = bundle
    # Three identical bytes with differing names stress canonical ordering.
    content = (folder / "factura_ñ.pdf").read_bytes()
    (folder / "z-copy.pdf").write_bytes(content)
    (folder / "a-copy.pdf").write_bytes(content)
    batch2 = service.ingest(folder, workbook, "Copias", "2026-09-19")["batch_id"]
    sid = service.batch(batch)["snapshot_id"]
    with service.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=? WHERE id=?", (sid, batch2))
    service.process(batch, ocr=False)
    service.process(batch2, ocr=False)
    for doc in service.store.all("SELECT * FROM documents"):
        current = service.detail(doc["id"])["decision"]
        assert current["human_anchor"] == service.evaluation(doc)["human_anchor"]
