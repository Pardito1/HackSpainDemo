"""Regression coverage for merging the v0.9 UI and teammates' main branch."""
import pytest
from fastapi.testclient import TestClient

from factu.db import Store
from factu.service import Service
from factu.presentation import invoice_activity
from factu.web import create_app
from test_workspace import processed, answer


def test_legacy_database_is_reused_without_an_empty_new_database(bundle):
    service, batch, *_ = bundle
    root = service.store.root
    service.store.path.rename(root / "alberto.sqlite3")
    reopened = Service(root)
    assert reopened.batch(batch)["id"] == batch
    assert reopened.store.path.name == "alberto.sqlite3"
    assert not (root / "factu.sqlite3").exists()
    assert reopened.store.verify_audit()["valid"]


def test_ambiguous_databases_are_not_silently_selected(tmp_path):
    for name in ("factu.sqlite3", "alberto.sqlite3"):
        (tmp_path / name).touch()
    with pytest.raises(ValueError, match="dos bases"):
        Store(tmp_path)


def test_withdrawal_keeps_audit_and_does_not_reactivate_older_response(bundle):
    service, batch, doc = processed(bundle)
    for result in ("NO_PAGAR", "ESCALAR"):
        args, preview = answer(service, doc, result)
        service.human_commit(*args, preview["preview_token"])
    service.retract_human_answer(doc["id"], "Marta", "La respuesta requiere una nueva comprobación.")
    detail = service.detail(doc["id"])
    assert detail["decision"]["result"] == "PAGAR"
    assert not detail["decision"].get("human_decision")
    assert len(detail["human_answers"]) == 2
    assert any(item["kind"] == "withdrawal" for item in invoice_activity(detail)["activity"])
    assert service.store.verify_audit()["valid"]
    with pytest.raises(ValueError, match="ninguna respuesta"):
        service.retract_human_answer(doc["id"], "Marta", "Intento repetido de la misma retirada.")


def test_merged_interface_keeps_sorting_and_withdrawal(bundle):
    service, batch, doc = processed(bundle)
    args, preview = answer(service, doc, "NO_PAGAR")
    service.human_commit(*args, preview["preview_token"])
    client = TestClient(create_app(service.store.root))
    page = client.get(f"/?batch={batch}&sort=total_asc").text
    assert "sort=total_desc" in page
    assert "supplier_asc" in page
    assert 'name="result" aria-label="Estado"' not in page
    page = client.get(f"/documents/{doc['id']}").text
    assert 'class="retract-form formgrid"' in page
    assert 'data-human-choice="PAGAR"' in page
    assert 'data-human-choice="ESCALAR"' not in page
    assert "Minutos dedicados" not in page
