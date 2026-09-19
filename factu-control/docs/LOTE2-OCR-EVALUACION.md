# Evaluación del OCR del lote 2

El perfil `lote2_ocr_v1` solo lee candidatos de los 40 PDFs nuevos. No decide
pagos ni corrige los datos por inferencia. Esta evaluación mide si sus campos
coinciden con transcripciones manuales internas revisadas de los originales;
una tasa de OCR no sustituye las reglas de pago ni el contraste con el ERP.

## Resultado reproducido para el lote público de 40 PDFs

La evaluación incluida usa transcripciones manuales internas revisadas de los
originales públicos en `evaluacion/lote2_labels.v1.json` y una partición
retrospectiva por proveedor en `evaluacion/lote2_splits.v1.json`. RapidOCR es
un modelo preentrenado: **no se ha hecho fine-tuning supervisado con estos 40
PDFs**. El primer split sirve para desarrollar las reglas de lectura, el
segundo para fijar el umbral y el tercero es un holdout interno agrupado. No
es una prueba ciega ni privada del jurado. Los `template_id` de este lote se
derivan del proveedor, por lo que `--strict-groups` acredita separación por
proveedor, no independencia de layout visual.

| Conjunto | PDFs | Exact match macro de campos | Expedientes con campos de riesgo autoaceptados por extracción y correctos frente a etiqueta |
| --- | ---: | ---: | ---: |
| Desarrollo (sin fine-tuning) | 15 | 100,0 % | 12/13 con todos los campos etiquetados |
| Validación | 15 | 93,33 % | 11/15 |
| Holdout interno agrupado | 10 | **99,0 %** | **8/10** |
| Total | 40 | 97,22 % | 31/38 elegibles; 31/40 = 77,50 % del lote |

En los 31 expedientes que el extractor marca completos, la precisión observada
de autoaceptación de lectura es 100 % (31/31). La cobertura segura es 81,58 %
entre los 38 expedientes con todos los campos de riesgo etiquetados y 77,50 %
(31/40) respecto del lote completo. Una ausencia confirmada, por ejemplo una
moneda no impresa, puede contar como *exact match* del campo si queda
`MISSING`, pero nunca como autoaceptación.

RapidOCR se ejecutó en 3 de las 42 páginas de esta corrida; las demás se
resolvieron con extracción local PyMuPDF. En modo `defects`, una ausencia de
campo crítico distinta de moneda puede solicitar el testigo en todas las
páginas del documento; no se promete que el OCR sea siempre solo una página.
Estos valores superan el umbral solicitado del 50 %, pero **no** son una
métrica de autorización de pagos, de RapidOCR aislado ni una afirmación de
generalización fuera de este lote público. El holdout tiene 10 documentos y
evita cruce de proveedor; el siguiente lote se medirá con el mismo protocolo
antes de ampliar la automatización.

El informe reproducido se guarda en `evaluacion/lote2_ocr_report.v1.json`.

## Protocolo para una evaluación independiente futura

1. Copiad `lote2_ocr_labels.template.json` y anotad cada valor mirando el PDF
   original, no la salida de FactU. Usad códigos ISO (`EUR`, `USD`, `JPY`),
   incluso si la factura está en español o contiene una dirección española.
   Un campo ausente se anota como `"value": null`; un campo no revisado se
   deja fuera del JSON.
2. Antes de ajustar expresiones, prompts o umbrales, agrupad los PDFs por
   `supplier_id` y, si está disponible, por un `template_id` que represente un
   layout visual realmente independiente. Asignad el grupo completo a `train`,
   `validation` o `test`: ningún proveedor ni layout independiente debe cruzar
   splits. En el lote público actual el template deriva del proveedor, por lo
   que solo se afirma aislamiento por proveedor.
3. En una evaluación futura, reservad `test` y no lo abráis para diseñar el extractor. Ajustad el perfil
   solo con `train`; elegid el umbral de autoaceptación solo con
   `validation`. Ejecutad `test` una vez al final con el código congelado. La
   partición incluida para el lote público es un holdout agrupado de desarrollo;
   no debe venderse como validación privada del jurado.
4. Haced una segunda revisión de una muestra de etiquetas y resolved las
   discrepancias antes de medir. No utilicéis `PAGAR`, `NO_PAGAR` o `ESCALAR`
   como supuesto *ground truth* de extracción.

La plantilla de splits es intencionadamente un ejemplo: sustituid sus tres
nombres por PDFs reales. El script se niega a medir si falta una etiqueta, si
un PDF pertenece a dos splits o si alguno de los tres splits está vacío.

## Ejecutar

```bash
python scripts/evaluate_lote2_ocr.py \
  --pdfs ../500-sombras-de-alberto/facturas_primin \
  --labels evaluacion/lote2_labels.v1.json \
  --splits evaluacion/lote2_splits.v1.json \
  --report evaluacion/lote2_ocr_report.v1.json \
  --strict-groups
```

`--strict-groups` comprueba que los `template_id` y `supplier_id` declarados no
se filtren de entrenamiento/validación a test; por sí solo no demuestra que un
template sea un layout visual distinto. El informe guarda hashes de PDFs,
labels, splits y código/dependencias relevantes, identidad del perfil, entorno
de ejecución, motores/modelos observados, métricas por split y errores con su
estado de extracción.

## Qué significa el informe

- **Exact match** compara el valor normalizado con la etiqueta (por ejemplo,
  `121,00` y `121.00` son el mismo importe; `USD` y `EUR`, no).
- **Autoaccept precision** responde: de los campos que el extractor marcó
  `OK`, ¿cuántos eran correctos?
- **Autoaccept coverage** responde: ¿qué proporción de campos etiquetados se
  pudo marcar `OK`? La **safe coverage** exige además que fueran correctos.
- La autoaceptación de una factura exige todos los campos de riesgo, sin
  alertas de OCR y sin instrucciones no fiables. El número de factura es
  informativo según la política v3.

Si no hay etiquetas manuales, el comando falla y no publica ninguna exactitud.
No reclaméis “más de 50 %” hasta informar la métrica de un holdout con el
número de documentos y campos etiquetados, y no confundáis esa métrica con la
validación privada del jurado.
