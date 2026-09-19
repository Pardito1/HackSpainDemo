"""Import/resume the official 40-document Saturday batch without mixing it into Lote 1."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .lote2_ocr import VERSION as LOTE2_EXTRACTION_VERSION
from .master import read_lote2_master
from .utils import digest, identifier


BATCH_NAME = "Lote 2 · 40 facturas"
PROFILE = "lote2_ocr_v1"
DOCUMENT_COUNT = 40


def _validate_erp_increment(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(
            f"No se encuentra la actualización ERP de Lote 2: {path}. "
            "Arranca el bridge con --lote2 erp_export_lote2.csv antes de procesar."
        )
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            rows = list(reader)
    except UnicodeDecodeError as exc:
        raise ValueError("erp_export_lote2.csv debe estar codificado en UTF-8") from exc
    required = {
        "asiento_id",
        "fecha_registro",
        "proveedor_id",
        "nif",
        "pedido",
        "importe_esperado",
        "estado",
    }
    if set(headers) != required or len(headers) != len(set(headers)) or len(rows) != DOCUMENT_COUNT:
        raise ValueError(
            "erp_export_lote2.csv no tiene el esquema o las 40 filas esperadas; "
            "no se puede comprobar que el bridge use la actualización oficial."
        )
    if any(not identifier(row.get("pedido")) for row in rows):
        raise ValueError("erp_export_lote2.csv contiene un pedido vacío")
    return path, rows


def validate_materials(materials):
    """Validate exactly the released Lote 2 source bundle, before any write."""
    root = Path(materials).expanduser().resolve()
    folder = root / "facturas_primin"
    workbook = root / "FINAL_v7_DEFINITIVO_ahorasi.xlsx"
    suppliers_csv = root / "proveedores_nuevos.csv"
    orders_csv = root / "pedidos_nuevos.csv"
    erp_increment = root / "erp_export_lote2.csv"
    if not workbook.is_file():
        raise ValueError(f"No se encuentra el Excel oficial: {workbook}")
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if len(files) != DOCUMENT_COUNT or len({p.name for p in files}) != DOCUMENT_COUNT:
        raise ValueError(
            f"Se esperaban {DOCUMENT_COUNT} PDFs con nombres únicos en {folder}; "
            f"encontrados: {len(files)}. No uses una carpeta de demo."
        )
    manifest = {}
    for file in files:
        content = file.read_bytes()
        if not content.startswith(b"%PDF") or len(content) > 50 * 1024 * 1024:
            raise ValueError(f"PDF inválido o demasiado grande: {file.name}")
        manifest[file.name] = digest(content)
    # Parse both incremental sources now, before any batch, blob or decision is
    # written.  This checks the schema and makes the expected order set explicit
    # for the later HTTP snapshot validation.
    master = read_lote2_master(workbook, suppliers_csv, orders_csv)
    _, erp_rows = _validate_erp_increment(erp_increment)
    csv_orders = {identifier(row["pedido"]) for row in erp_rows}
    supplemental_orders = {
        identifier(order["id"])
        for rows in master["orders"].values()
        for order in rows
        if order.get("source", {}).get("filename") == orders_csv.name
    }
    # The incremental ERP file may also update an older order (for example a
    # payment registered after Lote 1).  Every *new* master order must be
    # represented in the bridge update, but the ERP may legitimately contain
    # additional historical changes.
    if not supplemental_orders.issubset(csv_orders):
        raise ValueError(
            "pedidos_nuevos.csv contiene pedidos ausentes de erp_export_lote2.csv; "
            "no se puede conciliar una actualización incompleta."
        )
    return folder, workbook, suppliers_csv, orders_csv, erp_increment, manifest, master


def _source_signature(master):
    return {
        "base_excel": {"filename": master["filename"], "sha256": master["sha256"]},
        "supplemental": sorted(
            [
                {
                    key: source[key]
                    for key in ("kind", "filename", "sha256", "rows", "columns")
                }
                for source in master.get("supplemental_sources", [])
            ],
            key=lambda source: source["filename"],
        ),
    }


def prepare_batch(service, materials, as_of):
    """Create or resume Lote 2, preserving Lote 1 and any other batch intact."""
    (
        folder,
        workbook,
        suppliers_csv,
        orders_csv,
        _erp_increment,
        manifest,
        expected_master,
    ) = validate_materials(materials)
    candidates = [
        batch
        for batch in service.store.all("SELECT * FROM batches ORDER BY created")
        if batch["name"] == BATCH_NAME or batch.get("extraction_profile") == PROFILE
    ]
    if len(candidates) > 1:
        raise ValueError("Hay más de un Lote 2 en este estado. Conserva cada ejecución en una carpeta --data distinta.")
    if candidates:
        batch = candidates[0]
        actual = {
            row["file_id"]: row["sha256"]
            for row in service.store.all(
                "SELECT file_id,sha256 FROM documents WHERE batch_id=?", (batch["id"],)
            )
        }
        recorded_master = service.store.source(batch["master_id"])
        if (
            batch["name"] != BATCH_NAME
            or batch.get("extraction_profile") != PROFILE
            or batch["as_of"] != as_of
            or actual != manifest
            or _source_signature(recorded_master) != _source_signature(expected_master)
        ):
            raise ValueError(
                "El estado contiene otro Lote 2, un maestro incremental distinto o una fecha distinta. "
                "Usa otra carpeta --data; no borres la evidencia anterior."
            )
        documents = service.store.all(
            "SELECT extraction FROM documents WHERE batch_id=?", (batch["id"],)
        )
        if any(
            row["extraction"]
            and json.loads(row["extraction"]).get("version") != LOTE2_EXTRACTION_VERSION
            for row in documents
        ):
            raise ValueError(
                "Este Lote 2 se leyó con otra versión del extractor. Usa una carpeta --data nueva "
                "para conservar su historial y compararlo."
            )
        return batch["id"]

    # Store the two supplementary CSV originals independently, then reference
    # their hashes and exact rows from the composed master.  The base Excel
    # remains the XLSX preserved by Service.ingest.
    master = read_lote2_master(
        workbook, suppliers_csv, orders_csv, store_blob=service.store.blob
    )
    return service.ingest(
        folder,
        workbook,
        BATCH_NAME,
        as_of,
        profile=PROFILE,
        master_payload=master,
    )["batch_id"]


def run_lote2(service, materials, as_of, erp_url, user, password, emit=print):
    batch = prepare_batch(service, materials, as_of)
    emit(
        f"Lote {batch}: {DOCUMENT_COUNT} originales registrados con perfil {PROFILE}. "
        "Consultando el ERP completo actualizado…",
        flush=True,
    )
    snapshot = service.sync_erp(batch, erp_url, user, password)
    # The real bridge contains the initial 500+ records plus the 40-row
    # increment.  This prevents a visually similar demo ERP from being used.
    if snapshot["total"] < 500:
        raise ValueError(
            "El ERP no contiene el histórico completo. Arráncalo con "
            "alberto_erp.py --lote2 erp_export_lote2.csv, no con el ERP de demo."
        )
    _, _, _, _, erp_increment, _, _ = validate_materials(materials)
    _, increment_rows = _validate_erp_increment(erp_increment)
    required_orders = {identifier(row["pedido"]) for row in increment_rows}
    # ``sync_erp`` returns a compact receipt (id/count/retries); the complete
    # immutable rows live in the registered source.  Consult that source here
    # instead of accidentally relying on an implementation detail of the HTTP
    # client or a demo snapshot.
    snapshot_rows = service.store.source(snapshot["snapshot_id"])["rows"]
    available_orders = {identifier(row["pedido"]) for row in snapshot_rows}
    missing = sorted(required_orders - available_orders)
    if missing:
        preview = ", ".join(missing[:3])
        raise ValueError(
            "El snapshot HTTP no contiene los pedidos de la actualización Lote 2 "
            f"({preview}{'…' if len(missing) > 3 else ''}). Comprueba --lote2."
        )
    emit(
        f"ERP: {snapshot['total']} asientos, {snapshot['retries']} reintentos. "
        "Leyendo solo este Lote 2 con su perfil OCR…",
        flush=True,
    )
    service.retry(batch)
    while True:
        result = service.process(batch, ocr=True, limit=40)
        metrics = service.dashboard(batch)["metrics"]
        read = service.store.one(
            "SELECT COUNT(*) AS n FROM documents WHERE batch_id=? AND extraction IS NOT NULL",
            (batch,),
        )["n"]
        emit(
            f"Leídas: {read}/{DOCUMENT_COUNT} · con resultado: "
            f"{metrics['decisions']}/{DOCUMENT_COUNT}.",
            flush=True,
        )
        if result["processed"] == 0:
            break
    if metrics["pending"] or metrics["decisions"] != DOCUMENT_COUNT:
        raise ValueError(
            "Quedan facturas pendientes o con errores. Se conserva el avance; "
            "comprueba el OCR y vuelve a ejecutar el mismo comando."
        )
    rows = service.export_rows(batch)
    if len(rows) != DOCUMENT_COUNT or len({row["file_id"] for row in rows}) != DOCUMENT_COUNT:
        raise ValueError("La comprobación final no ha obtenido 40 resultados únicos.")
    audit = service.store.verify_audit()
    if not audit["valid"]:
        raise ValueError("La comprobación de integridad ha fallado; no se puede dar Lote 2 por terminado.")
    emit(
        "Terminado: 40 resultados únicos, perfil OCR trazable y registro de auditoría íntegro. "
        "Esto no certifica acierto frente a la referencia privada del reto.",
        flush=True,
    )
    return {"batch_id": batch, "profile": PROFILE, "metrics": metrics, "audit": audit}
