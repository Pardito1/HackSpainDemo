import json
from pathlib import Path
import openpyxl
import pymupdf as fitz
import pytest
from factu.service import Service
from scripts.validate_submission import check_jsonl, validate
from conftest import make_pdf, make_workbook, IBAN


def test_lote2_40_unseen_documents(tmp_path, erp_snapshot):
    """Size/layout-independent batch, independent of official filenames and labels."""
    folder = tmp_path / "lote2"
    folder.mkdir()
    workbook = tmp_path / "master.xlsx"
    make_workbook(workbook)
    book = openpyxl.load_workbook(workbook)
    rows = []
    for i in range(40):
        order = f"PO-2026-{9000+i}"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            (65, 80),
            "\n".join(
                [
                    f"Invoice # UNSEEN-{i:04}",
                    "Fecha factura: 01/02/2026",
                    "NIF: B12345678",
                    f"IBAN: {IBAN}",
                    f"Pedido: {order}",
                    "Subtotal: EUR 100.00",
                    "IVA (21%): EUR 21.00",
                    "TOTAL A PAGAR: EUR 121.00",
                ]
            ),
            fontsize=13,
        )
        doc.save(folder / f"nuevo-{i:02}.pdf")
        doc.close()
        book["Pedidos_2026"].append([order, "P001", "B12345678", 121, "PENDIENTE"])
        rows.append(erp_snapshot["rows"][0] | {"id": str(9000 + i), "pedido": order})
    book.save(workbook)
    book.close()
    service = Service(tmp_path / "state")
    batch = service.ingest(folder, workbook, "40 nuevos", "2026-09-19")["batch_id"]
    source = service.store.put_source("erp", erp_snapshot | {"rows": rows, "total": 40})
    with service.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=? WHERE id=?", (source, batch))
    assert service.process(batch, ocr=False)["decisions"] == 40
    outcomes = service.export_rows(batch)
    assert len(outcomes) == 40 and all(r["result"] == "PAGAR" for r in outcomes)
    assert service.store.verify_audit()["valid"]


def test_delivery_contract_and_duplicates(tmp_path):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    make_pdf(pdfs / "factura_ñ.pdf")
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    row = {"file_id": "factura_ñ.pdf", "result": "ESCALAR"}
    for name in ("outcomes.jsonl", "outcomes_lote2.jsonl"):
        (delivery / name).write_text(json.dumps(row) + "\n")
    make_pdf(delivery / "albertitos_plan.pdf")
    assert validate(delivery, pdfs, pdfs)["contract_valid"]
    (delivery / "outcomes.jsonl").write_text((json.dumps(row) + "\n") * 2)
    with pytest.raises(ValueError, match="duplicado"):
        check_jsonl(delivery / "outcomes.jsonl", pdfs)
    (delivery / "extra.txt").write_text("no corresponde")
    with pytest.raises(ValueError, match="exactamente"):
        validate(delivery, pdfs, pdfs)
