# Verificación realizada · 19 septiembre 2026

> Nota de vigencia (2026-09-20): este documento registra la verificación del 19/09. Tras el merge de moneda por IBAN ES y fechas en letras, la ejecución vigente del Lote 2 es 24 PAGAR / 1 NO_PAGAR / 15 ESCALAR y la suite tiene 345 pruebas Python + 15 de Node en verde. Ver README y `docs/CHANGELOG.md`.

## Actualización 0.10.0 · Lote 2 público (histórico del 19/09)

La ejecución integrada contra el bridge oficial arrancado con
`--lote2 erp_export_lote2.csv` validó 40 originales, Excel v7, proveedores y
pedidos incrementales, snapshot HTTP y perfil `lote2_ocr_v1`. Resultado del
corte con fecha `2026-09-19`: **19 PAGAR, 1 NO_PAGAR, 20 ESCALAR**, sin
pendientes y con auditoría válida. `PO-2026-0071` conserva sus dos asientos y
elige el último `PAGADA` únicamente porque proveedor/NIF/importe concuerdan y
la fecha máxima es única.

`python -m pytest -q` supera **279 pruebas Python** (dos avisos externos de
deprecación). `scripts/evaluate_lote2_ocr.py --strict-groups` mide el perfil
completo contra transcripciones manuales internas revisadas: 99,0 % de exact
match macro de campos en un holdout interno agrupado de 10 PDFs; 8/10
expedientes con campos de riesgo autoaceptados y correctos frente a etiqueta,
31/38 de cobertura segura entre expedientes elegibles y 31/40 (77,50 %) sobre
el lote completo. No es accuracy de pagos, de RapidOCR aislado ni validación
privada; la agrupación actual solo acredita proveedor, no layout visual
independiente. El informe trazable es
`evaluacion/lote2_ocr_report.v1.json`.

## Histórico · Actualización 0.7.0

153 pruebas Python y 6 JavaScript pasan. 500 documentos reevaluados con el histórico parcial incorporado, sin repetir lecturas ni aprobar pagos: 273 PAGAR, 9 NO_PAGAR, 218 ESCALAR. Se comprueban las 500 páginas de expediente, las pantallas principales y exportación de 500 nombres únicos. Integridad válida sobre 500 documentos, 3000 decisiones históricas, cinco fuentes y 501 blobs. El Excel original no se modifica. Los dos pedidos históricos no coinciden con los del lote, y no contienen identidad, número de factura ni estado de pago.

Comprobación en navegador: fuente Excel, campos condicionales de política, carga y comparación de actualización, confirmación e historial. Se corrige el refresco después de aplicar. Texto aumentado y vista a 390 px sin desbordamiento horizontal de página. El PDF refleja 0.7.0; los datos y benchmarks que siguen son históricos, no mediciones nuevas de rendimiento ni precisión.

## Actualización 0.4.0 (histórico)

127 pruebas Python y 4 JavaScript pasan. Prueba real: 500 PDFs / 522 páginas, 500 resultados únicos, 273 PAGAR / 9 NO_PAGAR / 218 ESCALAR, cero pendientes. 192 facturas tienen moneda MISSING: ya no se completa EUR sin evidencia. La auditoría comprueba originales, fuentes y decisiones sin incidencias. Las 500 rutas de expediente, las rutas de bandeja/fuentes/auditoría/operaciones/grupos y la exportación han respondido correctamente.

La vista de Alberto no contiene JSON ni hashes. El motivo se presenta antes del documento. Las evidencias técnicas se conservan en pantallas separadas. La comprobación visual se ha realizado en navegador y no se han registrado errores de consola en esa sesión. `albertitos_plan.pdf` ha sido actualizado a 0.4.0 y revisado visualmente en sus cuatro páginas. Guía: `../PROCESAR-500.md`.

## Registro histórico 0.3.1

115 pruebas Python y 4 JavaScript pasan. La prueba nueva ejecuta el generador distribuido, inicia el ERP sintético real por HTTP en un puerto local temporal, importa las facturas y verifica resultados, motivos, integridad y exportación. Casos: demo-1 PAGAR, demo-2 ESCALAR por IBAN, demo-3 NO_PAGAR por pago previo, demo-4 ESCALAR exclusivamente por instrucciones sospechosas. Las pruebas anteriores no cubrían el generador y no detectaron que añadía la frase maliciosa en las tres facturas.

Se verifican la tabla filtrada, sus contadores y la opción de quitar filtros. El generador sigue rechazando directorios existentes para conservar sus datos. El conjunto completo pasó en 9,07 segundos en el entorno macOS/Python 3.12; hay siete avisos de obsolescencia de dependencias. La conectividad de las nuevas pruebas es solo localhost.

La demo no modifica el primer lote oficial. Los recuentos de 500 facturas que siguen corresponden a verificaciones históricas. En aquella entrega el PDF era versión 0.3; ahora ha sido sustituido por el plan 0.4.0.

## Registro histórico 0.3 (conservado)

112 pruebas Python y 4 JavaScript pasan. Correcciones: campo OCR adyacente, etiquetas OCR, Excel dañado, JSON inválido (incluidos tipos anidados), respuesta no JSON/desconexión, errores ERP en vista previa y verificador de integridad. Pruebas de alteración aisladas comprueban originales, maestro, fuentes, decisiones, extracción/caché y respuestas humanas; las operaciones quedan bloqueadas.

Reprocesadas las 500 facturas con copia de seguridad previa: 430 PAGAR, 9 NO_PAGAR, 61 ESCALAR y cero pendientes técnicos. Cinco documentos con instrucciones sospechosas detectadas quedan en ESCALAR. `scan_001.pdf` extrae número `2026/86248` separado de fecha. Originales e intervenciones humanas intactos; historial anterior conservado. El plan PDF actual tiene siete páginas y cinco ADRs. Las métricas de rendimiento que siguen son históricas v0.2, no un benchmark extremo a extremo nuevo ni una medida de acierto.

## Registro histórico 0.2 (conservado)

## Pruebas automatizadas

68 pruebas pasan (5,56 s) en Python 3.12.14/macOS arm64, con RapidOCR instalado. Incluyen lectura OCR de una factura sintética rasterizada, evidencia/bbox, importes decimales, conflictos, protección frente a texto engañoso, reintentos HTTP, snapshot incompleto, recuperación de trabajo, unicidad de resultados, corrección humana y CSRF. Las 14 nuevas pruebas cubren respuesta de Alberto, caducidad, cambios selectivos, guardias, borradores descargables y anclaje estable de duplicados. Hay siete avisos de deprecación de dependencias, no fallos de tests.

La prueba `test_lote2_40_unseen_documents` genera 40 documentos sintéticos nuevos y verifica su procesamiento. **No son los 40 documentos oficiales del sábado**, ni certifica una norma v4 todavía desconocida.

## Prueba con el primer lote oficial

Materiales del repositorio `ikurotime/500-sombras-de-alberto`, commit inspeccionado `18d43b3ccee6802842c72054d5e5c8b8bb953949`:

- 500 PDFs, 522 páginas; 493 páginas con extracción nativa y 29 con OCR.
- Consulta del ERP por HTTP con latencia normal, sin `--rapido`: 516 registros en 26 páginas.
- Se conservaron y recuperaron errores HTTP 500 del ERP.
- 500 decisiones producidas, sin pendientes técnicos al finalizar.
- Distribución observada: 431 PAGAR, 9 NO_PAGAR y 60 ESCALAR.
- Auditoría encadenada verificada.

El informe actualizado `benchmark-v02.json` mide la versión 0.2: 46,967 segundos de extremo a extremo; 5,219 segundos de ERP; 30 intentos y 3 reintentos; 638,75 documentos/minuto en este lote; 1413,88 MiB de RSS máximo del proceso Python. Equipo macOS 15.1 arm64, 12 CPU lógicas, un worker, caché fría y ERP normal. El informe anterior `benchmark-lote1.json` se conserva como histórico 0.1. No es un compromiso de SLA ni una proyección validada a millones de documentos. El benchmark se ejecutó mientras había otras comprobaciones locales activas.

No hay etiquetas equivalentes del primer lote ni acceso a la referencia privada:
**no se ha medido accuracy de pagos ni se ha obtenido APTO oficial**. Lote 2
añade una medición interna del perfil de extracción, no una certificación. Los
casos escalados incluyen limitaciones reales del OCR y discrepancias de negocio;
no deben presentarse todos como anomalías correctamente detectadas sin revisión.

## Interfaz y empaquetado

Verificadas las rutas principales con FastAPI TestClient y comprobados visualmente la bandeja y un expediente con evidencia sobre el PDF. El resaltado se comprobó sobre el IBAN de `FA-9104_electricidad.pdf`. Los textos del PDF no se ejecutan ni alteran la política. Instalación editable y `pip check` satisfactorios.

El paquete no incluye base de datos de usuario, credenciales reales, PDFs
oficiales, resultados del jurado ni un JSONL estático generado fuera de un
estado auditado. El generador y ERP de demo son sintéticos y están identificados
como tales.

## Pendiente antes de presentar

1. Aprobar con el equipo los criterios de decisión y las precedencias de fuentes.
2. Revisar una muestra independiente de propuestas PAGAR y todos los escalados críticos; medir precisión por categoría y tiempo humano.
3. Repetir la evaluación de extracción con el próximo lote/una muestra externa antes de cambiar umbrales.
4. Comprobar que `docs/albertitos_plan.pdf` corresponde a v0.10.0 y regenerarlo solo si cambian métricas o ADRs.
5. Confirmar plazo y comprobar el repositorio de entrega separado.
