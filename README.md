# Esqueleto · decisión de facturas (HackSpain / 500 sombras de Alberto)

Sistema para decidir **PAGAR / NO_PAGAR / ESCALAR** sobre facturas PDF, un Excel de proveedores y un ERP de 2009. Este repo es el **esqueleto**: interfaces fijas + stubs, para que 4 personas implementen en paralelo sin pisarse.

El LLM, cuando exista, **solo verá campos estructurados** (`CamposExtraidos`). Nunca el PDF ni el texto crudo de la página. El texto libre (concepto, observaciones) llega etiquetado; si huele a prompt injection se **señala**, no se obedece.

## Cómo ejecutar

Desde la raíz del repo (Python 3.9+, solo librería estándar):

```bash
python main.py --reset-outputs --solo-demo
```

Escribe `outputs/outcomes.jsonl`, `outputs/trazabilidad.jsonl` y `outputs/revisor.html`. La cola queda en `estado/<file_id>.json`.

Una segunda ejecución **no reprocesa** las mismas facturas (idempotencia por `file_id` en estado `hecho`). Para forzar de nuevo: borra `estado/*.json` y usa `--reset-outputs`.

PDFs reales: colócalos en `entradas/`. El stub de P1 aún no los lee; seguirá devolviendo ejemplos.

ERP legado (cuando P3 deje de ser stub): `500-sombras-de-alberto-main/alberto_erp.py` y `MANUAL_ERP_2009.md`.

## División de trabajo

| Persona | Archivo | Qué implementa (los `TODO` del stub) |
| --- | --- | --- |
| **P1 Extracción** | `pipeline/extraccion.py` | PDF → capa de texto o OCR (pytesseract) → `CamposExtraidos` + confianza OCR + señales de manipulación/inyección |
| **P2 Reglas + Excel** | `pipeline/reglas.py` | Cruce determinista con `proveedores.xlsx` + normas → `DecisionParcial` (`PAGAR` / `NO_PAGAR` / `INDETERMINADO`) |
| **P3 ERP + estado** | `pipeline/erp_estado.py` | Bridge HTTP según el manual, cola `pendiente → procesando → pendiente_pregunta → respuesta → decidir → hecho \| error`, reintentos, duplicados |
| **P4 Salida + bonus** | `pipeline/salida.py` | `outcomes.jsonl`, `trazabilidad.jsonl`, vista de revisor (ESCALAR, preguntas, duplicados) |

`main.py` orquesta. No pongáis reglas en P1 ni HTTP del ERP en P2. No os importéis entre módulos: solo `pipeline.interfaces`.

## Interfaces (contratos)

Definidas en `pipeline/interfaces.py`. Resumen:

```
PDF + file_id
    → P1 extraer_campos()            → CamposExtraidos
    → P2 aplicar_reglas(campos, xlsx) → DecisionParcial
    → P3 consultar_erp(campos)        → ResultadoERP
         verificar_duplicado(file_id)  → InfoDuplicado   (antes de extraer)
         transicionar_estado(...)      → RegistroEstado
    → main consolida                  → Outcome (PAGAR | NO_PAGAR | ESCALAR + Pregunta[])
    → P4 escribir_salidas()           → JSONL + revisor.html
```

| Función | Recibe | Devuelve |
| --- | --- | --- |
| `extraer_campos(ruta_pdf, file_id)` | PDF, id | `CamposExtraidos` (nunca texto de página crudo) |
| `aplicar_reglas(campos, ruta_excel)` | campos, Excel | `DecisionParcial` + `que_falta` si INDETERMINADO |
| `consultar_erp(campos)` | campos | `ResultadoERP` + lista de `ConsultaERP` |
| `verificar_duplicado(file_id, dir)` | id, `estado/` | `InfoDuplicado` |
| `transicionar_estado(...)` | id, estado, error | `RegistroEstado` persistido |
| `escribir_salidas(outcome, traza, dir)` | decisión + traza | append JSONL; actualiza revisor |

`result` de cada línea de `outcomes.jsonl` es solo `PAGAR`, `NO_PAGAR` o `ESCALAR`. Preguntas y el resto de evidencia van **en la misma línea** como campos extra.

Cola P3: `pendiente → procesando → pendiente_pregunta → respuesta → decidir → hecho`. Cualquier excepción: `error` (con timestamp e `intentos`); `main.py` reintenta hasta 3 veces.

## Formato de salida (ejemplo)

Tres líneas ficticias ya están en `outputs/` para ver el esquema sin ejecutar nada. Tras `python main.py --reset-outputs --solo-demo` se regeneran con timestamps reales.

## Regla de oro

Si tu código necesita un tipo del vecino, **añádelo en `interfaces.py`** y avisa. No copies dataclasses a tu módulo.
