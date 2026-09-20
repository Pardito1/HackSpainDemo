"""Lo que la pantalla «En vivo» necesita saber, leído de SQLite en una pasada.

La pantalla sondea cada 500 ms mientras el lote corre, así que aquí no se abre
ningún PDF ni se toca el ERP: son nueve consultas medidas sobre las 500 del
lote 1 (13,6 ms en total). Nunca se selecciona `decisions.payload` entero —
cada fila pesa 17 kB de media— sino los dos datos que se enseñan.
"""

from statistics import median

PIPELINE = [
    ("discover", "descubrir"),
    ("extract", "extraer"),
    ("normalize", "normalizar"),
    ("enrich", "enriquecer"),
    ("decide", "decidir"),
    ("persist", "persistir"),
    ("export", "exportar"),
]

# Qué etapa del dibujo se enciende con el trabajo que está corriendo.
ACTIVE_STAGE = {
    "Procesar": "extract",
    "Recuperar": "extract",
    "Reevaluar": "decide",
    "ERP": "enrich",
}

# Trabajos que deciden facturas. Sincronizar el ERP no decide ninguna, así que
# dividir las 500 ya decididas entre sus 3,7 s daría 135 docs/s: un número que
# no es el ritmo de nada y que se enseña en la pantalla del jurado.
DECIDING = {"Procesar", "Recuperar", "Reevaluar"}

# Las doce últimas se eligen ANTES de calcular las columnas derivadas: con las
# subconsultas dentro del SELECT principal, SQLite las evalúa para las 1.000
# decisiones del lote y la consulta pasa de 3,9 ms a 97,6 ms.
RECENT = """
WITH top AS MATERIALIZED (
  SELECT de.rowid rn, de.id, de.result, de.document_id
    FROM decisions de JOIN documents d ON d.id=de.document_id
   WHERE d.batch_id=? ORDER BY de.rowid DESC LIMIT 12)
SELECT d.file_id, d.id doc_id, top.result,
       (SELECT json_extract(r.value,'$.id')
          FROM decisions x, json_each(x.payload,'$.rules') r
         WHERE x.id=top.id AND json_extract(r.value,'$.state')='FAIL'
         LIMIT 1) first_failed_rule,
       CASE WHEN json_extract(d.extraction,'$.model_usage') IS NOT NULL THEN 'modelo'
            WHEN EXISTS(SELECT 1 FROM json_each(d.extraction,'$.pages') p
                        WHERE json_extract(p.value,'$.method') LIKE 'rapidocr%') THEN 'ocr'
            ELSE 'texto' END method,
       (SELECT coalesce(sum(c.seconds),0) FROM costs c WHERE c.document_id=d.id) seconds
  FROM top JOIN documents d ON d.id=top.document_id
 ORDER BY top.rn DESC
"""


def live(service, batch_id, run):
    batch = service.batch(batch_id)
    store = service.store
    totals = store.one(
        "SELECT count(*) documents, sum(latest_decision IS NOT NULL) decided,"
        " sum(state='HUMAN_REVIEW') human_review FROM documents WHERE batch_id=?",
        (batch_id,),
    )
    documents = totals["documents"]
    decided = totals["decided"] or 0
    jobs = {
        row["state"]: row["n"]
        for row in store.all(
            "SELECT j.state, count(*) n FROM jobs j JOIN documents d ON d.id=j.document_id"
            " WHERE d.batch_id=? GROUP BY j.state",
            (batch_id,),
        )
    }
    results = {"PAGAR": 0, "NO_PAGAR": 0, "ESCALAR": 0}
    for row in store.all(
        "SELECT de.result, count(*) n FROM documents d"
        " JOIN decisions de ON de.id=d.latest_decision"
        " WHERE d.batch_id=? GROUP BY de.result",
        (batch_id,),
    ):
        results[row["result"]] = row["n"]

    seconds_by_stage = {}
    for row in store.all(
        "SELECT stage, seconds FROM costs WHERE batch_id=?", (batch_id,)
    ):
        seconds_by_stage.setdefault(row["stage"], []).append(row["seconds"] or 0)
    stages = {
        stage: {
            "count": len(values),
            "p50_s": round(median(values), 4),
            "max_s": round(max(values), 4),
        }
        for stage, values in sorted(seconds_by_stage.items())
    }

    model = store.one(
        "SELECT count(*) runs, coalesce(sum(json_extract(payload,'$.neurons')),0) neurons,"
        " coalesce(sum(external_eur),0) eur FROM costs"
        " WHERE batch_id=? AND stage='modelo'",
        (batch_id,),
    )
    # El modelo lee las páginas sin texto y, si MODELO_PAGINAS_TEXTO está
    # encendida, también las demás: la extracción guarda cuál de las dos fue.
    # Contarlas cuesta 17 ms sobre las 500 (hay que abrir cada extracción), así
    # que si el modelo no ha corrido en este lote no se pregunta: son cero.
    model_pages = 0
    if model["runs"]:
        model_pages = store.one(
            "SELECT count(*) n FROM documents d, json_each(d.extraction,'$.pages') p"
            " WHERE d.batch_id=? AND json_extract(d.extraction,'$.model_usage') IS NOT NULL"
            " AND (json_extract(p.value,'$.needs_ocr')=1"
            "      OR json_extract(d.extraction,'$.engines.modelo.paginas_texto')=1)",
            (batch_id,),
        )["n"]
    warnings = {
        row["code"]: row["n"]
        for row in store.all(
            "SELECT json_extract(w.value,'$.code') code, count(*) n"
            " FROM documents d, json_each(d.extraction,'$.warnings') w"
            " WHERE d.batch_id=? GROUP BY code ORDER BY n DESC",
            (batch_id,),
        )
    }

    elapsed = run.get("elapsed_s") or 0
    deciding = run.get("task") in DECIDING
    return {
        "batch": {
            "id": batch["id"],
            "name": batch["name"],
            "as_of": batch["as_of"],
            "policy": store.source(batch["policy_id"])["version"],
        },
        "run": run,
        "totals": {
            "documents": documents,
            # `process` extrae las 40 y decide las 40 al final, en un solo paso:
            # sin este número la barra se queda en cero 27 de los 28 segundos.
            "extracted": jobs.get("DONE", 0),
            "decided": decided,
            "pending": documents - decided,
            "running": jobs.get("RUNNING", 0),
            "failed": jobs.get("ERROR", 0) + jobs.get("RETRY_WAIT", 0),
            "human_review": totals["human_review"] or 0,
        },
        "results": results,
        "throughput_docs_per_s": round(decided / elapsed, 2) if elapsed and deciding else None,
        "stages": stages,
        "pipeline": [
            {"id": key, "label": label, "active": run.get("active") and ACTIVE_STAGE.get(run.get("task")) == key}
            for key, label in PIPELINE
        ],
        "cost": {
            "neurons": model["neurons"],
            "external_eur": round(model["eur"], 6),
            "model_pages": model_pages,
        },
        "warnings": warnings,
        "recent": [
            {
                "file_id": row["file_id"],
                "doc_id": row["doc_id"],
                "result": row["result"],
                "first_failed_rule": row["first_failed_rule"],
                "seconds": round(row["seconds"], 3),
                "method": row["method"],
            }
            for row in store.all(RECENT, (batch_id,))
        ],
    }
