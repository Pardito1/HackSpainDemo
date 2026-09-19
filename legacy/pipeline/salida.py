"""P4 - SALIDA + BONUS (vista de revisor).

Responsable: outcomes.jsonl, trazabilidad.jsonl y la lista humana de
ESCALAR / preguntas / duplicados sospechosos.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from pipeline.interfaces import (
    InfoDuplicado,
    Outcome,
    ResultadoFinal,
    Traza,
)


def _linea_outcome(outcome: Outcome) -> dict:
    """Una sola linea JSON: obligatorios + extras en el mismo objeto."""
    fila = {
        "file_id": outcome.file_id,
        "result": outcome.result.value,
        "razonamiento": outcome.razonamiento,
        "confianza": outcome.confianza,
        "preguntas": [asdict(p) for p in outcome.preguntas],
    }
    fila.update(outcome.extras)
    return fila


def _linea_traza(traza: Traza) -> dict:
    return {
        "file_id": traza.file_id,
        "estado": traza.estado.value,
        "timestamps": traza.timestamps,
        "evidencia": traza.evidencia,
        "versiones": traza.versiones,
        "consultas_erp": traza.consultas_erp,
    }


def _append_jsonl(ruta: Path, objeto: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(objeto, ensure_ascii=False) + "\n")


def _actualizar_revisor(
    directorio_outputs: Path,
    outcome: Outcome,
    duplicados: list[InfoDuplicado],
) -> None:
    """Bonus: vista HTML minima para Alberto (ESCALAR, preguntas, duplicados)."""
    ruta = directorio_outputs / "revisor.html"
    outcomes_path = directorio_outputs / "outcomes.jsonl"
    filas_escalar: list[dict] = []
    if outcomes_path.exists():
        for linea in outcomes_path.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            obj = json.loads(linea)
            if obj.get("result") == ResultadoFinal.ESCALAR.value:
                filas_escalar.append(obj)

    bloques_escalar = []
    for obj in filas_escalar:
        preguntas = obj.get("preguntas") or []
        lis = "".join(f"<li>{p.get('texto', p)}</li>" for p in preguntas)
        bloques_escalar.append(
            f"<article><h3>{obj['file_id']}</h3>"
            f"<p>{obj.get('razonamiento', '')}</p>"
            f"<p>confianza={obj.get('confianza')}</p>"
            f"<ul>{lis}</ul></article>"
        )

    bloques_dup = []
    for d in duplicados:
        if d.es_duplicado:
            bloques_dup.append(
                f"<li>{d.file_id} -> {d.file_id_original}: {d.motivo}</li>"
            )

    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Revisor - facturas</title>
<style>
 body {{ font-family: sans-serif; max-width: 720px; margin: 2rem auto; }}
 article {{ border: 1px solid #ccc; padding: 1rem; margin: 1rem 0; }}
</style></head><body>
<h1>Cola de revisor (bonus)</h1>
<p>Ultima factura escrita: <strong>{outcome.file_id}</strong> -> {outcome.result.value}</p>
<h2>ESCALAR y preguntas</h2>
{''.join(bloques_escalar) or '<p>Ninguna.</p>'}
<h2>Duplicados sospechosos</h2>
<ul>{''.join(bloques_dup) or '<li>Ninguno en esta ejecucion.</li>'}</ul>
</body></html>
"""
    ruta.write_text(html, encoding="utf-8")


def escribir_salidas(
    outcome: Outcome,
    traza: Traza,
    directorio_outputs: Path,
    duplicados_sospechosos: list[InfoDuplicado] | None = None,
) -> None:
    """Stub P4 con escritura real de JSONL + HTML de revisor.

    TODO(P4):
      - Validar que cada linea tiene file_id y result en {PAGAR, NO_PAGAR, ESCALAR}.
      - No pisar outcomes de un lote anterior sin politica explicita (append vs lote2).
      - Enriquecer evidencia (hashes PDF, version de extractor, coste LLM).
      - Vista de revisor: filtros, evidencia lado a lado, responder preguntas
        y reinyectar a estado `respuesta` -> `decidir`.
      - Separar outcomes.jsonl / outcomes_lote2.jsonl segun la Caja.
    """
    _append_jsonl(directorio_outputs / "outcomes.jsonl", _linea_outcome(outcome))
    _append_jsonl(directorio_outputs / "trazabilidad.jsonl", _linea_traza(traza))
    _actualizar_revisor(
        directorio_outputs,
        outcome,
        duplicados_sospechosos or [],
    )
