"""Import/resume the 500-document initial batch; never mix it with demo state."""
from __future__ import annotations

import json
from pathlib import Path

from .extract import VERSION
from .utils import digest


def validate_materials(materials):
    root = Path(materials).expanduser().resolve()
    folder = root / "facturas"
    workbook = root / "FINAL_v7_DEFINITIVO_ahorasi.xlsx"
    if not workbook.is_file():
        raise ValueError(f"No se encuentra el Excel oficial: {workbook}")
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if len(files) != 500 or len({p.name for p in files}) != 500:
        raise ValueError(f"Se esperaban 500 PDFs con nombres únicos en {folder}; encontrados: {len(files)}. No uses demo-input.")
    manifest = {}
    for file in files:
        content = file.read_bytes()
        if not content.startswith(b"%PDF") or len(content) > 50 * 1024 * 1024:
            raise ValueError(f"PDF inválido o demasiado grande: {file.name}")
        manifest[file.name] = digest(content)
    return folder, workbook, manifest


def prepare_batch(service, materials, as_of):
    folder, workbook, manifest = validate_materials(materials)
    batches = service.store.all("SELECT * FROM batches ORDER BY created")
    if not batches:
        return service.ingest(folder, workbook, "Lote inicial · 500 facturas", as_of)["batch_id"]
    if len(batches) != 1:
        raise ValueError("Usa una carpeta de estado exclusiva para las 500 facturas, sin la demo ni otros lotes.")
    batch = batches[0]
    documents = service.store.all("SELECT file_id,sha256,extraction FROM documents WHERE batch_id=?", (batch["id"],))
    actual = {d["file_id"]: d["sha256"] for d in documents}
    master = service.store.source(batch["master_id"])
    if (actual != manifest or master["sha256"] != digest(workbook.read_bytes()) or batch["as_of"] != as_of):
        raise ValueError("El estado contiene otro lote, un Excel distinto o una fecha distinta. Usa otra carpeta --data; no borres el estado anterior.")
    if any(d["extraction"] and json.loads(d["extraction"])["version"] != VERSION for d in documents):
        raise ValueError("Este lote se leyó con una versión anterior. Usa una carpeta --data nueva para conservar su historial y aplicar las correcciones.")
    return batch["id"]


def run_lote1(service, materials, as_of, erp_url, user, password, emit=print):
    batch = prepare_batch(service, materials, as_of)
    emit(f"Lote {batch}: 500 originales registrados. Consultando el ERP completo…", flush=True)
    snapshot = service.sync_erp(batch, erp_url, user, password)
    # The official initial ERP has more than 500 records; 3/4 would be the demo.
    if snapshot["total"] < 500:
        raise ValueError(f"El ERP solo devuelve {snapshot['total']} asientos. Comprueba que arrancaste el ERP oficial, no scripts/demo_erp.py.")
    emit(f"ERP: {snapshot['total']} asientos, {snapshot['retries']} reintentos. Leyendo los PDF con OCR cuando hace falta…", flush=True)
    service.retry(batch)
    while True:
        result = service.process(batch, ocr=True, limit=50)
        metrics = service.dashboard(batch)["metrics"]
        read = service.store.one("SELECT COUNT(*) AS n FROM documents WHERE batch_id=? AND extraction IS NOT NULL", (batch,))["n"]
        emit(f"Leídas: {read}/500 · con resultado: {metrics['decisions']}/500. Las decisiones se publican al completar las lecturas para comprobar duplicados.", flush=True)
        if result["processed"] == 0:
            break
    if metrics["pending"] or metrics["decisions"] != 500:
        raise ValueError("Quedan facturas pendientes o con errores. Se conserva el avance. Comprueba el OCR y vuelve a ejecutar el mismo comando; no borres la carpeta de estado.")
    rows = service.export_rows(batch)
    if len(rows) != 500 or len({r["file_id"] for r in rows}) != 500:
        raise ValueError("La comprobación final no ha obtenido 500 resultados únicos.")
    audit = service.store.verify_audit()
    if not audit["valid"]:
        raise ValueError("La comprobación de integridad ha fallado; no se puede dar el lote por terminado.")
    emit("Terminado: 500 resultados únicos y registro de auditoría íntegro. Esto no certifica acierto frente a la referencia privada del reto.", flush=True)
    return {"batch_id": batch, "metrics": metrics, "audit": audit}
