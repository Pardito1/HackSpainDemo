import json
import sqlite3
from pathlib import Path
import pytest
from factu.service import Service
from factu.utils import canonical
from conftest import make_pdf


def first(service):
    return service.store.one("SELECT * FROM documents ORDER BY created,id")


def test_roundtrip_and_idempotence(bundle, tmp_path):
    service, batch, _, _ = bundle
    assert service.process(batch, ocr=False)["decisions"] == 1
    assert service.export_rows(batch) == [
        {"file_id": "factura_ñ.pdf", "result": "PAGAR"}
    ]
    n = service.store.one("SELECT count(*) n FROM decisions")["n"]
    service.process(batch, ocr=False)
    service.evaluate_batch(batch)
    assert service.store.one("SELECT count(*) n FROM decisions")["n"] == n
    path = tmp_path / "outcomes.jsonl"
    service.export(batch, path)
    assert json.loads(path.read_text())["file_id"] == "factura_ñ.pdf"
    assert service.store.verify_audit()["valid"]


def test_pending_export_blocked(bundle):
    service, batch, _, _ = bundle
    with pytest.raises(ValueError):
        service.export_rows(batch)


def test_worker_crash_and_lease_recovery(bundle):
    service, batch, _, _ = bundle
    with pytest.raises(KeyboardInterrupt):
        service.process(batch, ocr=False, fault_after=0)
    assert service.claim(batch) is None  # no stealing a live lease
    assert service.retry(batch)["requeued"] == 0
    with service.store.connect() as db:
        db.execute("UPDATE jobs SET lease_until=0")
    restarted = Service(service.store.root)
    assert restarted.process(batch, ocr=False)["decisions"] == 1
    assert restarted.store.one("SELECT attempts FROM jobs")["attempts"] == 2
    assert restarted.store.verify_audit()["valid"]


def test_append_only_audit(bundle):
    service, *_ = bundle
    with pytest.raises(sqlite3.IntegrityError):
        with service.store.connect() as db:
            db.execute('UPDATE events SET kind="tampered"')


def test_duplicate_across_batches_single_obligation(bundle):
    service, batch, folder, workbook = bundle
    service.process(batch, ocr=False)
    second = service.ingest(folder, workbook, "Second", "2026-09-19")["batch_id"]
    with pytest.raises(ValueError):
        service.export_rows(batch)
    with service.store.connect() as db:
        db.execute(
            "UPDATE batches SET snapshot_id=? WHERE id=?",
            (service.batch(batch)["snapshot_id"], second),
        )
    service.process(second, ocr=False)
    assert service.export_rows(batch)[0]["result"] == "PAGAR"
    assert service.export_rows(second)[0]["result"] == "NO_PAGAR"
    assert (
        service.store.one("SELECT count(*) n FROM costs WHERE stage='extract_cache'")[
            "n"
        ]
        == 1
    )


def test_nonidentical_same_order_escalates_both(bundle, tmp_path):
    service, batch, _, workbook = bundle
    service.process(batch, ocr=False)
    newfolder = tmp_path / "second"
    newfolder.mkdir()
    make_pdf(newfolder / "other.pdf", extra="Otra versión del documento")
    second = service.ingest(newfolder, workbook, "Second", "2026-09-19")["batch_id"]
    with service.store.connect() as db:
        db.execute(
            "UPDATE batches SET snapshot_id=? WHERE id=?",
            (service.batch(batch)["snapshot_id"], second),
        )
    service.process(second, ocr=False)
    assert service.export_rows(batch)[0]["result"] == "ESCALAR"
    assert service.export_rows(second)[0]["result"] == "ESCALAR"


def test_human_preview_commit_and_stale_preview(bundle):
    service, batch, _, _ = bundle
    service.process(batch, ocr=False)
    doc = first(service)
    args = ([doc["id"]], "total", "125,00", "Ana", "Verificado en la factura original")
    preview = service.preview_review(*args)
    assert preview["previews"][0]["after"] == "ESCALAR"
    service.commit_review(*args, preview["preview_token"])
    current = service.detail(doc["id"])
    assert current["extraction"]["fields"]["total"]["value"] == "121.00"
    assert current["decision"]["fields"]["total"]["value"] == "125.00"
    assert len(current["history"]) == 2
    with pytest.raises(ValueError, match="cambió"):
        service.commit_review(*args, preview["preview_token"])


def test_policy_replay_does_not_rerun_ocr(bundle, tmp_path):
    service, batch, _, _ = bundle
    service.process(batch, ocr=False)
    policy = service.store.source(service.batch(batch)["policy_id"])
    policy["version"] = "v4-test"
    policy["extra_rules"] = [
        {
            "id": "limit",
            "field": "total",
            "op": "lte",
            "value": "100",
            "question": "Confirma límite.",
        }
    ]
    path = tmp_path / "v4.json"
    path.write_text(json.dumps(policy))
    before = service.store.one("SELECT count(*) n FROM extraction_cache")["n"]
    service.change_policy(batch, path, "Equipo")
    assert service.export_rows(batch)[0]["result"] == "ESCALAR"
    assert service.store.one("SELECT count(*) n FROM extraction_cache")["n"] == before


def test_reextract_preserves_history(bundle):
    service, batch, _, _ = bundle
    service.process(batch, ocr=False)
    service.reextract(batch)
    with pytest.raises(ValueError):
        service.export_rows(batch)
    service.process(batch, ocr=False)
    assert service.export_rows(batch)[0]["result"] == "PAGAR"
    assert service.store.verify_audit()["valid"]


def test_reextract_leaves_the_other_batches_decided(bundle, erp_snapshot):
    """Los dos lotes de la entrega viven en el mismo `--data`.

    Reextraer el lote 1 para releer los 29 escaneados no puede dejar al lote 2
    sin decisiones: son 40 facturas ya exportadas que nadie ha pedido rehacer.
    """
    service, first, folder, workbook = bundle
    service.process(first, ocr=False)
    second = service.ingest(folder, workbook, "Otro", "2026-09-19")["batch_id"]
    snapshot_id = service.store.put_source("erp", erp_snapshot)
    with service.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=? WHERE id=?", (snapshot_id, second))
    service.process(second, ocr=False)
    decided = service.export_rows(second)

    service.reextract(first)

    assert service.export_rows(second) == decided
    with pytest.raises(ValueError):
        service.export_rows(first)


def test_workflow_lock_between_instances(bundle):
    import fcntl

    service, batch, _, _ = bundle
    with (service.store.root / "workflow.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="trabajo activo"):
            Service(service.store.root).process(batch)
