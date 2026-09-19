# FactU · HackSpainDemo · v0.10.0

**El producto es [`factu-control/`](factu-control/) — empieza por su README.** El resto de este repo son materiales del reto, análisis y prototipos archivados.

## Cifras vigentes (2026-09-20, MacBook Air M1, ERP oficial con latencia real, sin modelo externo)

- Lote 1 (500 facturas): **435 PAGAR / 9 NO_PAGAR / 56 ESCALAR**, extremo a extremo en **53,8 s**.
- Lote 2 (40 facturas): **24 PAGAR / 1 NO_PAGAR / 15 ESCALAR**, extremo a extremo en **8,3 s**.
- Pruebas: **345 pruebas Python + 15 de Node** en verde (28,3 s en el mismo M1).
- Coste externo de inferencia: **0 €** (RapidOCR local, sin llamadas al proveedor `modelo`). No es coste total.

Los repartos son aplicación de la política v3 sobre las fuentes registradas ese día; no son métrica de precisión frente a la referencia privada del jurado. La documentación completa y el histórico están en [`factu-control/README.md`](factu-control/README.md) y [`factu-control/docs/CHANGELOG.md`](factu-control/docs/CHANGELOG.md).

## Mapa del repo

| Ruta | Qué es |
|---|---|
| [`factu-control/`](factu-control/) | Producto: app local FastAPI + CLI, SQLite, OCR local, política JSON versionada, revisión humana, benchmark y validador de entrega. |
| [`analisis-del-reto/`](analisis-del-reto/) | Reconocimiento del entorno hecho el viernes: trampas medidas del reto (`HALLAZGOS.md`) y mapa de instrucciones inyectadas en los PDFs (`INYECCIONES.md`). |
| [`500-sombras-de-alberto-main/`](500-sombras-de-alberto-main/) | Materiales oficiales del reto (500 PDFs, Excel `FINAL_v7_DEFINITIVO_ahorasi.xlsx`, `alberto_erp.py`, manual). **No se modifican.** |
| [`entrega-parcial-v0.9.1/`](entrega-parcial-v0.9.1/) | Instantánea histórica: resultados y plan de 0.9.1. No es la ejecución vigente. |
| `pruebas/`, `referencia/` | Ensayos y ficheros de comparación de decisiones. |
| [`legacy/`](legacy/) | Prototipo P1–P4 archivado completo: `pipeline/`, `main.py`, `outputs/`, `tests/`, `ver.py`, `requirements.txt`, `entradas/`, `estado/`. |

## Repositorio de entrega

El repositorio de entrega del concurso es **otro**: `manchadito09/HackSpain`. Contiene exactamente tres ficheros en su raíz — `outcomes.jsonl`, `outcomes_lote2.jsonl`, `albertitos_plan.pdf` — y **ningún código, credencial ni ejecutable**. Aquí, en el repo de código, nunca se suben credenciales ni los datos del reto procesados; allí, nunca código.
