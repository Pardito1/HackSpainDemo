import pytest

from factu.lote1 import prepare_batch, validate_materials
from factu.service import Service
from conftest import make_workbook


def materials(tmp_path, count):
    root = tmp_path / "materials"
    (root / "facturas").mkdir(parents=True)
    make_workbook(root / "FINAL_v7_DEFINITIVO_ahorasi.xlsx")
    for i in range(count):
        (root / "facturas" / f"invoice-{i}.pdf").write_bytes(b"%PDF-1.4\n")
    return root


def test_refuse_demo_or_incomplete_materials(tmp_path):
    root = materials(tmp_path, 4)
    with pytest.raises(ValueError, match="500 PDFs"):
        validate_materials(root)


def test_prepare_resumes_without_duplicating_the_500_records(tmp_path):
    root = materials(tmp_path, 500)
    service = Service(tmp_path / "state")
    batch = prepare_batch(service, root, "2026-09-19")
    assert prepare_batch(service, root, "2026-09-19") == batch
    assert len(service.store.all("SELECT id FROM documents")) == 500
    assert len(service.store.all("SELECT id FROM batches")) == 1
    (root / "facturas" / "invoice-0.pdf").write_bytes(b"%PDF-1.4\nchanged\n")
    with pytest.raises(ValueError, match="otro lote"):
        prepare_batch(service, root, "2026-09-19")
    assert service.store.verify_audit()["valid"]


def test_prepare_resumes_lote1_when_the_versioned_lote2_also_exists(tmp_path):
    root = materials(tmp_path, 500)
    service = Service(tmp_path / "state")
    initial = prepare_batch(service, root, "2026-09-19")
    lote2_folder = tmp_path / "lote2"
    lote2_folder.mkdir()
    (lote2_folder / "lote2.pdf").write_bytes(b"%PDF-1.4\n")
    service.ingest(
        lote2_folder,
        root / "FINAL_v7_DEFINITIVO_ahorasi.xlsx",
        "Lote 2 · 40 facturas",
        "2026-09-19",
        profile="lote2_ocr_v1",
    )

    assert prepare_batch(service, root, "2026-09-19") == initial
    assert len(service.store.all("SELECT id FROM batches")) == 2
    assert service.store.verify_audit()["valid"]
