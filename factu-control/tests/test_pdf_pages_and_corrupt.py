import json

import pymupdf as fitz

from factu.extract import extract_pdf
from factu.service import Service
from conftest import IBAN, make_workbook


def make_two_page_pdf(path):
    doc = fitz.open()
    first = doc.new_page()
    first.insert_text(
        (50, 50),
        "\n".join(
            [
                "Factura: DEMO-002",
                "Fecha: 01/02/2026",
                "Proveedor: Empresa de prueba",
                "NIF: B12345678",
                f"IBAN: {IBAN}",
                "Pedido: PO-2026-0001",
                "Base imponible: 100,00",
                "IVA (21%): 21,00",
            ]
        ),
        fontsize=12,
    )
    second = doc.new_page()
    second.insert_text(
        (50, 50),
        "Continuación de la factura DEMO-002\nTOTAL: 121,00\nMoneda: EUR",
        fontsize=12,
    )
    doc.save(path)
    doc.close()


def test_two_pages_total_on_second_page(tmp_path):
    path = tmp_path / "dos_paginas.pdf"
    make_two_page_pdf(path)
    extraction = extract_pdf(path, ocr=False)
    assert len(extraction["pages"]) == 2
    assert extraction["fields"]["total"]["value"] == "121.00"
    assert extraction["fields"]["total"]["evidence"][0]["page"] == 2
    assert extraction["fields"]["base"]["value"] == "100.00"


def test_non_pdf_ingests_and_escalates(tmp_path, erp_snapshot):
    folder = tmp_path / "pdfs"
    folder.mkdir()
    (folder / "no_es_pdf.pdf").write_bytes(b"esto no es un PDF\n")
    workbook = tmp_path / "maestro.xlsx"
    make_workbook(workbook)
    service = Service(tmp_path / "state")
    batch = service.ingest(folder, workbook, "Corrupto", "2026-09-19")["batch_id"]
    snapshot_id = service.store.put_source("erp", erp_snapshot)
    with service.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=? WHERE id=?", (snapshot_id, batch))
    service.process(batch, ocr=False)
    extraction = json.loads(
        service.store.one("SELECT extraction FROM documents")["extraction"]
    )
    assert any(w["code"] == "PDF_CORRUPT" for w in extraction["warnings"])
    assert service.export_rows(batch) == [
        {"file_id": "no_es_pdf.pdf", "result": "ESCALAR"}
    ]
