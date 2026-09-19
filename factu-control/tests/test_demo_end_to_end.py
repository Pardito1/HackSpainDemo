"""Exercise the distributed demo scripts, their actual HTTP ERP and the UI."""

import importlib.util
import json
from http.server import HTTPServer
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from factu.service import Service
from factu.web import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def demo_bundle(tmp_path):
    inputs = tmp_path / "demo-input"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/make_demo.py"), "--output", str(inputs)],
        check=True, capture_output=True, text=True,
    )
    assert sorted(p.name for p in (inputs / "facturas").glob("*.pdf")) == [
        "demo-1.pdf", "demo-2.pdf", "demo-3.pdf", "demo-4.pdf",
    ]
    spec = importlib.util.spec_from_file_location("bundled_demo_erp", ROOT / "scripts/demo_erp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = HTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        service = Service(tmp_path / "state")
        batch = service.ingest(inputs / "facturas", inputs / "maestro.xlsx", "Demo sintética", "2026-09-19")["batch_id"]
        service.sync_erp(batch, f"http://127.0.0.1:{server.server_port}", "alberto", "FACTURAS2009")
        service.process(batch, ocr=False)
        yield service, batch
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bundled_demo_has_four_distinct_cases(demo_bundle):
    service, batch = demo_bundle
    rows = service.export_rows(batch)
    assert {r["file_id"]: r["result"] for r in rows} == {
        "demo-1.pdf": "PAGAR", "demo-2.pdf": "ESCALAR",
        "demo-3.pdf": "NO_PAGAR", "demo-4.pdf": "ESCALAR",
    }
    for doc in service.store.all("SELECT * FROM documents"):
        extraction = json.loads(doc["extraction"])
        assert bool(extraction["untrusted_instructions"]) == (doc["file_id"] == "demo-4.pdf")
        if doc["file_id"] == "demo-4.pdf":
            decision = json.loads(service.store.one("SELECT payload FROM decisions WHERE id=?", (doc["latest_decision"],))["payload"])
            assert [r["id"] for r in decision["rules"] if r["state"] != "PASS"] == ["document_instructions"]
    metrics = service.dashboard(batch)["metrics"]
    assert metrics["documents"] == 4 and metrics["pending"] == 0
    assert metrics["counts"] == {"PAGAR": 1, "NO_PAGAR": 1, "ESCALAR": 2}
    assert metrics["external_eur"] == 0
    assert service.store.verify_audit()["valid"]


def test_filtered_demo_explains_counts_and_reset(demo_bundle):
    service, batch = demo_bundle
    with TestClient(create_app(service.store.root)) as client:
        paid = client.get("/", params={"batch": batch, "result": "PAGAR"})
        assert paid.status_code == 200
        assert "Propuestas de pago <span" in paid.text
        assert "Mostrando <strong>1</strong> de <strong>4</strong> facturas" in paid.text
        assert "Quitar filtros" in paid.text
        empty = client.get("/", params={"batch": batch, "result": "PENDING"})
        assert "Mostrando <strong>0</strong> de <strong>4</strong> facturas" in empty.text
        assert "No hay facturas con estos filtros." in empty.text
        assert "Ver consultas pendientes" in empty.text
        all_rows = client.get("/", params={"batch": batch})
        assert "Todas las facturas <span" in all_rows.text
        for i in range(1, 5):
            assert f"demo-{i}.pdf" in all_rows.text


def test_demo_generator_preserves_existing_directory(tmp_path):
    folder = tmp_path / "existing"
    folder.mkdir()
    sentinel = folder / "keep.txt"
    sentinel.write_text("existing data")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/make_demo.py"), "--output", str(folder)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "directorio ya existe" in result.stderr
    assert sentinel.read_text() == "existing data"
    assert sorted(p.name for p in folder.iterdir()) == ["keep.txt"]
