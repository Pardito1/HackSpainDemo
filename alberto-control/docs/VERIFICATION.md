# Verificación realizada · 19 septiembre 2026

## Actualización verificada 0.3

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

No hay etiquetas independientes del primer lote ni acceso a la referencia privada: **no se ha medido accuracy ni se ha obtenido APTO oficial**. Los casos escalados incluyen limitaciones reales del OCR y discrepancias de negocio; no deben presentarse todos como anomalías correctamente detectadas sin revisión.

## Interfaz y empaquetado

Verificadas las rutas principales con FastAPI TestClient y comprobados visualmente la bandeja y un expediente con evidencia sobre el PDF. El resaltado se comprobó sobre el IBAN de `FA-9104_electricidad.pdf`. Los textos del PDF no se ejecutan ni alteran la política. Instalación editable y `pip check` satisfactorios.

El paquete no incluye base de datos de usuario, credenciales reales, PDFs oficiales, resultados del jurado ni un JSONL inventado del segundo lote. El generador y ERP de demo son sintéticos y están identificados como tales.

## Pendiente antes de presentar

1. Aprobar con el equipo los criterios de decisión y las precedencias de fuentes.
2. Revisar una muestra independiente de propuestas PAGAR y todos los escalados críticos; medir precisión por categoría y tiempo humano.
3. Incorporar datos/ERP/norma oficiales del lote 2 y ejecutar regresiones.
4. El `docs/albertitos_plan.pdf` refleja la versión 0.3. Actualizarlo de nuevo tras el lote 2 y cualquier cambio posterior.
5. Confirmar plazo y comprobar el repositorio de entrega separado.
