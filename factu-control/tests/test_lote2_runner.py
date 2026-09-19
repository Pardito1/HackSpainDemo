import csv
import json

import pytest

from factu.lote2 import BATCH_NAME, DOCUMENT_COUNT, PROFILE, prepare_batch, validate_materials
from factu.service import Service
from conftest import IBAN, make_workbook


def official_materials(tmp_path, count=DOCUMENT_COUNT):
    root = tmp_path / "official-lote2"
    pdfs = root / "facturas_primin"
    pdfs.mkdir(parents=True)
    make_workbook(root / "FINAL_v7_DEFINITIVO_ahorasi.xlsx")
    for index in range(count):
        (pdfs / f"lote2-{index:02}.pdf").write_bytes(b"%PDF-1.4\n")
    with (root / "proveedores_nuevos.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ID", "Razon Social", "NIF", "IBAN", "Ciudad", "Condiciones"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "P012",
                "Razon Social": "Proveedor nuevo",
                "NIF": "DE812345678",
                "IBAN": "DE89370400440532013000",
                "Ciudad": "Hamburg",
                "Condiciones": "30 dias",
            }
        )
    order_rows = []
    with (root / "pedidos_nuevos.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["pedido", "proveedor_id", "nif", "importe_total", "estado", "fecha_pedido"],
        )
        writer.writeheader()
        for index in range(count - 1):
            row = {
                "pedido": f"PO-2026-{500 + index:04}",
                "proveedor_id": "P012",
                "nif": "DE812345678",
                "importe_total": "121.00",
                "estado": "ABIERTO",
                "fecha_pedido": "2026-08-20",
            }
            writer.writerow(row)
            order_rows.append(row)
    with (root / "erp_export_lote2.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["asiento_id", "fecha_registro", "proveedor_id", "nif", "pedido", "importe_esperado", "estado"],
        )
        writer.writeheader()
        for index, order in enumerate(order_rows):
            writer.writerow(
                {
                    "asiento_id": f"AS-9{index:04}",
                    "fecha_registro": "2026-09-01",
                    "proveedor_id": order["proveedor_id"],
                    "nif": order["nif"],
                    "pedido": order["pedido"],
                    "importe_esperado": order["importe_total"],
                    "estado": "PENDIENTE",
                }
            )
        # An ERP incremental can also record a change to an old Lote 1 order.
        writer.writerow(
            {
                "asiento_id": "AS-OLD",
                "fecha_registro": "2026-09-01",
                "proveedor_id": "P001",
                "nif": "B12345678",
                "pedido": "PO-2026-0001",
                "importe_esperado": "121.00",
                "estado": "PAGADA",
            }
        )
    return root


def test_lote2_prepares_40_pdfs_and_preserves_incremental_provenance(tmp_path):
    root = official_materials(tmp_path)
    service = Service(tmp_path / "state")
    # A normal batch is allowed to coexist with Lote 2 in the same state.
    other = tmp_path / "other"
    other.mkdir()
    (other / "other.pdf").write_bytes(b"%PDF-1.4\n")
    service.ingest(other, root / "FINAL_v7_DEFINITIVO_ahorasi.xlsx", "Otro lote", "2026-09-19")

    batch = prepare_batch(service, root, "2026-09-19")
    assert prepare_batch(service, root, "2026-09-19") == batch
    record = service.batch(batch)
    assert record["name"] == BATCH_NAME
    assert record["extraction_profile"] == PROFILE
    assert service.store.one("SELECT count(*) n FROM documents WHERE batch_id=?", (batch,))["n"] == DOCUMENT_COUNT
    master = service.store.source(record["master_id"])
    assert master["filename"] == "FINAL_v7_DEFINITIVO_ahorasi.xlsx"
    assert master["sha256"]
    assert [(source["filename"], source["rows"]) for source in master["supplemental_sources"]] == [
        ("proveedores_nuevos.csv", 1),
        ("pedidos_nuevos.csv", DOCUMENT_COUNT - 1),
    ]
    assert all(source.get("blob") for source in master["supplemental_sources"])
    assert master["suppliers"]["P012"][0]["source"]["filename"] == "proveedores_nuevos.csv"
    assert master["orders"]["PO-2026-0500"][0]["source"]["filename"] == "pedidos_nuevos.csv"
    assert service.store.verify_audit()["valid"]


def test_lote2_rejects_missing_or_incomplete_official_materials(tmp_path):
    root = official_materials(tmp_path, count=DOCUMENT_COUNT - 1)
    with pytest.raises(ValueError, match="40 PDFs"):
        validate_materials(root)


def test_profile_is_sealed_into_event_cost_cache_and_reextract_scope(tmp_path, monkeypatch):
    root = official_materials(tmp_path)
    service = Service(tmp_path / "state")
    batch = prepare_batch(service, root, "2026-09-19")
    other = tmp_path / "other"
    other.mkdir()
    (other / "other.pdf").write_bytes(b"%PDF-1.4\n")
    normal_workbook = tmp_path / "normal.xlsx"
    make_workbook(normal_workbook)
    normal = service.ingest(other, normal_workbook, "Normal", "2026-09-19")["batch_id"]
    snapshot = service.store.put_source(
        "erp",
        {
            "complete": True,
            "total": 1,
            "pages": [],
            "rows": [
                {
                    "id": "1",
                    "fecha": "2026-02-01",
                    "proveedor": "P001",
                    "nif": "B12345678",
                    "pedido": "PO-2026-0001",
                    "importe": "121.00",
                    "estado": "PENDIENTE",
                }
            ],
        },
    )
    with service.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=? WHERE id=?", (snapshot, normal))
    seen = []

    def fake_extract(path, ocr=True, profile="standard"):
        seen.append(profile)
        values = {
            "invoice_number": "TEST-1",
            "supplier_nif": "B12345678",
            "iban": IBAN,
            "order": "PO-2026-0001",
            "date": "2026-02-01",
            "base": "100.00",
            "tax_rate": "21.00",
            "tax_amount": "21.00",
            "total": "121.00",
            "currency": "EUR",
        }
        return {
            "version": "native-rapidocr-lote2-v1" if profile == PROFILE else "native-test",
            "profile": profile,
            "fields": {
                field: {
                    "value": value,
                    "status": "OK",
                    "evidence": [{"method": "pymupdf", "value": value}],
                }
                for field, value in values.items()
            },
            "pages": [{"method": "rapidocr-lote2"}],
            "warnings": [],
            "engines": {"profile": profile},
        }

    monkeypatch.setattr("factu.service.extract_pdf", fake_extract)
    # Pending jobs in Lote 2 do not block an already complete normal batch.
    assert service.process(normal, ocr=False)["decisions"] == 1
    assert service.store.one(
        "SELECT latest_decision FROM documents WHERE batch_id=?", (normal,)
    )["latest_decision"] is not None
    service.process(batch, ocr=False, limit=1)
    assert seen == ["standard", PROFILE]
    event = service.store.one(
        "SELECT payload FROM events WHERE kind='extracted' AND batch_id=? ORDER BY id DESC LIMIT 1",
        (batch,),
    )
    assert json.loads(event["payload"])["profile"] == PROFILE
    cost = service.store.one("SELECT payload FROM costs WHERE batch_id=? AND stage='extract'", (batch,))
    cost_payload = json.loads(cost["payload"])
    assert cost_payload["profile"] == PROFILE
    assert cost_payload["ocr_used"] is True
    # Re-extracting Lote 2 must not invalidate the separately evaluated batch.
    # Capture this after processing Lote 2: cross-batch duplicate detection is
    # intentionally allowed to publish a newer decision for the normal batch.
    normal_decision = service.store.one(
        "SELECT latest_decision FROM documents WHERE batch_id=?", (normal,)
    )["latest_decision"]
    assert normal_decision is not None
    service.reextract(batch)
    assert service.store.one(
        "SELECT latest_decision FROM documents WHERE batch_id=?", (normal,)
    )["latest_decision"] == normal_decision
