"""La pantalla «En vivo»: el esquema que sondea cada 500 ms y su plantilla."""

import pytest
from fastapi.testclient import TestClient

from factu.service import Service
from factu.web import create_app
from conftest import make_pdf, make_workbook

ESQUEMA = {
    "batch", "run", "totals", "results", "throughput_docs_per_s",
    "stages", "pipeline", "cost", "warnings", "recent",
}


@pytest.fixture
def client(bundle):
    service, batch, *_ = bundle
    service.process(batch, ocr=False)
    with TestClient(create_app(service.store.root)) as client:
        yield client, service, batch


def test_the_live_endpoint_answers_the_whole_schema_over_a_decided_batch(client):
    client, service, batch = client
    data = client.get(f"/api/batches/{batch}/live").json()
    assert set(data) == ESQUEMA
    assert data["batch"]["name"] == "Test" and data["batch"]["policy"]
    assert data["run"] == {"active": False, "task": None, "started": None, "elapsed_s": 0}
    assert data["totals"] == {
        "documents": 1, "extracted": 1, "decided": 1, "pending": 0,
        "running": 0, "failed": 0, "human_review": 0,
    }
    assert sum(data["results"].values()) == 1
    assert set(data["results"]) == {"PAGAR", "NO_PAGAR", "ESCALAR"}
    assert [stage["id"] for stage in data["pipeline"]][0] == "discover"
    assert not any(stage["active"] for stage in data["pipeline"])
    assert set(data["cost"]) == {"neurons", "external_eur", "model_pages"}
    assert data["stages"]["extract"]["count"] == 1
    assert set(data["stages"]["extract"]) == {"count", "p50_s", "max_s"}
    row = data["recent"][0]
    assert row["file_id"] == "factura_ñ.pdf"
    assert set(row) == {"file_id", "doc_id", "result", "first_failed_rule", "seconds", "method"}
    assert row["method"] == "texto" and row["seconds"] >= 0
    assert client.get(f"/documents/{row['doc_id']}").status_code == 200


def test_an_ingested_batch_with_no_decisions_still_answers(tmp_path):
    folder = tmp_path / "pdfs"
    folder.mkdir()
    make_pdf(folder / "factura_ñ.pdf")
    workbook = tmp_path / "maestro.xlsx"
    make_workbook(workbook)
    service = Service(tmp_path / "state")
    batch = service.ingest(folder, workbook, "Vacío", "2026-09-19")["batch_id"]
    with TestClient(create_app(service.store.root)) as client:
        data = client.get(f"/api/batches/{batch}/live").json()
    assert set(data) == ESQUEMA
    assert data["totals"] == {
        "documents": 1, "extracted": 0, "decided": 0, "pending": 1,
        "running": 0, "failed": 0, "human_review": 0,
    }
    assert data["results"] == {"PAGAR": 0, "NO_PAGAR": 0, "ESCALAR": 0}
    # Sin run no se inventa un ritmo: cero decididos entre cero segundos no es 0,0 docs/s.
    assert data["throughput_docs_per_s"] is None
    assert data["recent"] == [] and data["stages"] == {}
    assert data["cost"] == {"neurons": 0, "external_eur": 0, "model_pages": 0}


def test_an_unknown_batch_is_rejected(client):
    client, *_ = client
    assert client.get("/api/batches/no-existe/live").status_code == 400


def test_the_live_page_renders_with_its_own_assets_and_no_inline_script(client):
    client, service, batch = client
    html = client.get("/live", params={"batch": batch}).text
    assert "/static/live.css" in html and "/static/live.js" in html
    assert "<script>" not in html
    assert 'id="live" data-batch="%s"' % batch in html
    assert "<span>En vivo</span>" in html
    for result in ("PAGAR", "NO_PAGAR", "ESCALAR"):
        assert 'data-count="%s"' % result in html
    for stage in ("descubrir", "extraer", "decidir", "exportar"):
        assert stage in html


def test_the_live_page_does_not_crash_without_batches(tmp_path):
    with TestClient(create_app(tmp_path / "state")) as client:
        response = client.get("/live")
    assert response.status_code == 200
    assert "Todavía no hay ningún lote" in response.text


def test_a_finished_run_keeps_its_total_time_instead_of_resetting(client):
    client, service, batch = client
    assert client.post(
        f"/api/batches/{batch}/evaluate",
        headers={"X-CSRF-Token": service.store.csrf_token},
    ).status_code == 200
    for _ in range(50):
        data = client.get(f"/api/batches/{batch}/live").json()
        if not data["run"]["active"]:
            break
    assert data["run"]["task"] == "Reevaluar" and data["run"]["started"]
    assert data["run"]["elapsed_s"] > 0
    assert client.get(f"/api/batches/{batch}/live").json()["run"]["elapsed_s"] == data["run"]["elapsed_s"]
