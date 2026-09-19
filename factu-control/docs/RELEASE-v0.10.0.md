# FactU 0.10.0 · Lote 2, OCR aislado y decisiones seguras

> Nota de vigencia (2026-09-20): las cifras de esta nota corresponden a la ejecución de la release. Tras el PR #28 (moneda por IBAN ES, fechas en letras), la ejecución vigente del Lote 2 es 24 PAGAR / 1 NO_PAGAR / 15 ESCALAR y la suite tiene 345+15 pruebas. Ver README.

## Resultado

Se incorpora el lote público de 40 facturas sin alterar el recorrido del lote
inicial de 500. La prueba end-to-end usa el bridge oficial con
`erp_export_lote2.csv`, procesa los 40 documentos y verifica la cadena de
auditoría:

| Resultado | Facturas |
| --- | ---: |
| `PAGAR` | 19 |
| `NO_PAGAR` | 1 |
| `ESCALAR` | 20 |
| Total | 40 |

La única propuesta `NO_PAGAR` corresponde a `PO-2026-0071`: conserva los dos
asientos ERP, selecciona el más reciente por fecha (`PAGADA`, 2026-09-01) solo
porque proveedor, NIF e importe coinciden, y guarda las dos filas como
evidencia. Una fecha empatada, un importe/identidad distinto o una fecha/estado
inválido produce `ESCALAR`.

## Perfil de extracción `lote2_ocr_v1`

- Se fija en el lote al importarlo. El lote de 500 mantiene el perfil
  `standard`; no se reextrae ni cambia su caché.
- Lee el texto nativo con PyMuPDF y usa el modelo local RapidOCR/ONNX como
  **segundo testigo** cuando hay defecto de lectura, imagen dominante o riesgo
  de anotación. Si falta un campo crítico no monetario, el modo `defects` puede
  recorrer todas las páginas del documento; en la ejecución medida corrió en
  3 de 42 páginas. Cada testigo conserva texto, página, caja, método y
  confianza.
- Reconoce etiquetas de factura en ES, EN, CA, PT, FR, IT y DE y divisas ISO
  explícitas `EUR`, `USD`, `JPY`, `GBP`, `CHF`, `BRL` y `MXN`.
- No es un modelo fine-tuned con las 40 facturas: es RapidOCR preentrenado más
  parsing determinista y validación de dominio. Por eso se mide con etiquetas
  humanas y se limita su alcance al lote publicado.
- La identidad de caché contiene perfil, versión, modo OCR y umbrales. Cambiar
  entre el modo económico `defects` y el modo exhaustivo `always` no reutiliza
  evidencia incompatible.

## Criterios de automatización

`PAGAR` requiere todos los controles deterministas: campos suficientes,
identidad y cuenta contra maestro, pedido/importe/estado ERP, aritmética,
fecha, moneda permitida, ausencia de duplicado y ausencia de señales de
manipulación. El OCR lee; el código decide.

Se escala cuando falta o contradice evidencia: moneda no impresa/ambigua,
divisa extranjera sin FX trazable, texto de instrucción no fiable, IBAN no
autorizado, asiento ERP ambiguo, discrepancia de identidad/importe, escritura
manual, tachón o corrección. No se infiere EUR de que una factura esté en
español, tenga NIF/IBAN español o diga `Tokyo, España` / `Sao Paulo, Spain`.

Una divisa extranjera queda correctamente extraída y trazada, pero v3 solo
autoriza EUR: el ERP legado no declara la divisa ni un tipo de cambio. Una
norma futura de FX debe aportar importe nativo, fuente/timestamp de conversión,
importe EUR y pruebas antes de poder aprobarla.

## Evaluación de extracción

`evaluacion/lote2_labels.v1.json` contiene transcripciones manuales internas
revisadas de los originales y `evaluacion/lote2_splits.v1.json` es una
partición retrospectiva por proveedor entre train/validation/holdout. Los
`template_id` actuales derivan del proveedor, así que no acreditan layouts
visuales independientes. El protocolo y el informe completo están en
[`LOTE2-OCR-EVALUACION.md`](LOTE2-OCR-EVALUACION.md).

En el holdout agrupado (10 PDFs), el exact match macro de los diez campos
evaluados es **99,0 %**. Ocho de diez expedientes tenían los campos de riesgo
autoaceptados por extracción y los ocho coincidieron con su etiqueta. En los
40 PDFs, la cobertura segura es 31/38 (81,58 %) entre expedientes elegibles y
31/40 (77,50 %) respecto al lote completo. Esta es una métrica del perfil de
extracción de campos, no de RapidOCR aislado, precisión de pagos o garantía
para datos no observados; el holdout interno no sustituye la validación privada
del jurado y el próximo lote debe repetir el protocolo antes de modificar
umbrales.

## Verificación

```bash
python -m pytest -q
python scripts/evaluate_lote2_ocr.py \
  --pdfs ../500-sombras-de-alberto/facturas_primin \
  --labels evaluacion/lote2_labels.v1.json \
  --splits evaluacion/lote2_splits.v1.json \
  --report evaluacion/lote2_ocr_report.v1.json \
  --strict-groups
```

En la revisión de esta versión: **279 pruebas Python** superadas (dos avisos de
deprecación de dependencias) y auditoría válida en la ejecución completa de
Lote 2.
