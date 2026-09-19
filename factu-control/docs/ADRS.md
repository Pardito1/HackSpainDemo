# ADRs y trade-offs · decisiones de esta implementación

Estos ADRs describen el código, no capacidades futuras como si estuvieran terminadas. La propuesta anterior del chat sugería otras bibliotecas/componentes; aquí se documenta la elección efectivamente implementada.

Actualización 0.3 de ADR-01/02/04/05: las instrucciones sospechosas detectadas obligan a consulta y su resolución requiere confirmación humana explícita; los controles bancarios siguen protegidos. La extracción separa etiquetas de fecha adyacentes y rechaza identificadores mezclados. El verificador comprueba originales, fuentes, decisiones y registros sellados además de la cadena de eventos, y bloquea operaciones si detecta alteraciones. Se acepta cobertura parcial de registros antiguos sin sello y se comunica; no se promete firma externa ni detector universal. Evidencia: `test_regressions_v03.py` y `test_frontend.mjs`.

Actualización 0.4.0: no se asume moneda cuando no está impresa. Se conserva la ausencia y se solicita confirmación con autor, motivo y fuente; el valor humano no se presenta como leído. La interfaz de Alberto se separa de la auditoría técnica sin eliminar evidencia ni añadir una falsa barrera de permisos. Evidencia: `test_currency_and_alberto_ui.py` y `test_lote1_runner.py`. Trade-off aceptado: más consultas (218 en el lote medido) a cambio de no inventar divisas.

Actualización 0.10.0: Lote 2 usa el perfil aislado `lote2_ocr_v1`, con
RapidOCR como segundo testigo local cuando la lectura nativa tiene defectos.
No se asume EUR por idioma/país y las divisas extranjeras se conservan sin
convertir mientras no exista FX trazable. El ERP puede exponer historial del
mismo pedido: se conserva entero y solo se usa su asiento más reciente si es
único y consistente. Evidencia: `test_lote2_ocr.py`, `test_lote2_runner.py`,
`test_policy.py` y `docs/LOTE2-OCR-EVALUACION.md`.

## ADR-01 · Reglas explícitas y abstención; sin decisor LLM

Actualización 0.7 de ADR-01/03/05: se contrasta el ID completo de pedido con `Pedidos_2025_OLD`. Alternativas descartadas: ignorar el histórico o rechazar por importe coincidente. Se elige alerta revisable con celdas de origen, sin confundir un archivo parcial de dos pedidos con un registro de pagos. La vista previa invalida únicamente dependencias históricas coincidentes; duplicados entre lotes se indexan una vez por comparación. Alberto puede resolver la alerta con evidencia y confirmación expresa; la aplicación no autentica al revisor. Evidencia: `test_history_and_sources_ui.py` y comprobación del lote de 500 sin repetir OCR. Consecuencia aceptada: más consultas si aparecen coincidencias, y cobertura limitada al histórico aportado.

**Contexto:** las facturas contienen texto engañoso; la norma deja parte de los criterios al equipo. Un resultado muy seguro sin evidencia puede producir un pago indebido.

**Alternativas:** agente autónomo que decide; LLM extractor más reglas; parser/OCR más reglas y revisión humana.

**Decisión:** última opción. PAGAR exige controles; el motor limita NO_PAGAR a pago confirmado/copia exacta, y escala las demás anomalías. Alberto puede aportar una respuesta de negocio con motivo y evidencia; no puede saltarse controles bancarios/técnicos. El equipo debe aprobar estas semánticas. Datos PDF no pueden modificar política ni actuar sobre ERP.

**Consecuencias:** reproducibilidad, cero inferencia generativa facturada, menos flexibilidad semántica y mayor revisión en escaneos difíciles. No se afirma haber construido un orquestador multiagente ni un failover LLM.

**Evidencia:** `test_policy.py`: instrucciones no autoritativas, tolerancia exacta, emisor frente a cliente, fuentes contradictorias, fecha inválida y chequeos de salida. Los tests no son etiquetas del jurado.

## ADR-02 · Texto nativo + RapidOCR/ONNX local, con procedencia

**Contexto:** primer lote con 500 PDFs y 522 páginas, de las que 29 requieren OCR. Hay imágenes degradadas y formatos diversos.

**Alternativas:** OCR a todo; servicio cloud de documentos; PaddleOCR completo; RapidOCR/ONNX selectivo.

**Decisión:** PyMuPDF conserva palabras y coordenadas; OCR local solo para páginas sin texto suficiente o con imagen dominante. RapidOCR sustituye al runtime PaddleOCR propuesto inicialmente por una instalación CPU más acotada. Los modelos incluidos se identifican con hashes. No se descarga un modelo nuevo según el contenido de la factura.

**Consecuencias:** arranque sin API keys, no enviar facturas a terceros y menor trabajo en páginas nativas. Se aceptan límites de idioma, geometría y calidad. Umbral OCR heurístico; no completar datos por coincidencia con ERP. PyMuPDF tiene condiciones de licencia que revisar antes de explotación comercial.

**Evidencia:** benchmark del lote completo; pruebas de bbox, original/normalizado, ambigüedad y página rasterizada. La lectura OCR exitosa no equivale a extracción correcta de todos los campos.

## ADR-03 · ERP HTTP y snapshots íntegros por lote

**Contexto:** el bridge presenta latencia, paginación, sesiones y errores ORA-00600; Excel y ERP discrepan en algunas identidades.

**Alternativas:** leer los datos internos del script; consultar por factura; snapshot paginado y versionado.

**Decisión:** snapshot HTTP completo, sin saltarse el bridge. Ritmo acotado, reintentos para 429/500/timeout, renovación en 401, validación de recuentos y IDs únicos. Una sincronización fallida no publica resultados parciales ni conserva como vigente una decisión anterior del lote.

**Consecuencias:** amortiza consultas, permite reproducir decisiones; el snapshot tiene una fecha y puede envejecer. No hay operación de pago contra un dato supuestamente en tiempo real. Un snapshot completo no garantiza consistencia transaccional si el ERP cambia filas sin cambiar sus metadatos durante la lectura; con este bridge el lote es estable, en producción haría falta versión de corte o exportación consistente.

**Evidencia:** pruebas HTTP 401/429/500/timeout y snapshot incompleto; benchmark consulta 516 registros en 26 páginas con ERP normal. Los XML originales se conservan para inspección.

**Evolución 0.2:** los cambios se preparan sin alterar fuentes vigentes; una previsualización fallida no se aplica. La confirmación conserva lo no afectado y reevalúa las dependencias que cambiaron, sin OCR. Política nueva implica revisión de todas las reglas. Nueva norma textual necesita aprobación explícita de su correspondencia con código. El cambio de fuentes es requisito principal, no bonus.

## ADR-04 · SQLite, un worker y recuperación conservadora

**Contexto:** tiempo de hackathon limitado; se necesita estado durable, no perder trabajo y evitar carreras entre CLI e interfaz.

**Alternativas:** estado en memoria; PostgreSQL + Redis/Celery desde el inicio; SQLite WAL, cola local y bloqueo de workflow.

**Decisión:** SQLite, transacciones, eventos append-only encadenados, caché por contenido/versiones, lease de 10 minutos y token de propietario. Un solo flujo de escritura; lecturas concurrentes. Barrera hasta terminar extracciones para detectar duplicados entre lotes.

**Consecuencias:** instalación sencilla, recuperación verificable; el volumen grande y muchos operadores requieren rediseñar la cola/coordinar un publicador transaccional. Un expediente atascado puede impedir finalizar otros lotes; preferimos hacer visible ese límite a afirmar exactamente-una-vez inexistente. El historial local no es WORM ni una prueba invulnerable a administradores.

**Evidencia:** reinicio tras extracción y antes de commit, imposibilidad de robar lease vivo, idempotencia, duplicados interlote y bloqueo entre instancias en `test_service.py`.

## ADR-05 · Alberto decide con evidencia; el sistema conserva el contexto

**Contexto:** preguntar es una salida legítima. Resolver un campo no debe saltarse el resto de controles. Una causa común puede repetirse y costar tiempo a Alberto.

**Alternativas:** botón «aprobar todo»; editar datos sobrescribiendo; corrección versionada con vista previa y reevaluación individual.

**Decisión:** corrección de lectura y respuesta de negocio separadas. Actor, motivo y referencia obligatorios; previsualización dependiente del contexto; historial intacto. La respuesta conserva el resultado original del motor. Si cambia el fundamento, vuelve a ESCALAR y se pide ratificación. PAGAR no salta controles de cuenta, importe, identidad, duplicados o pagos previos. La resolución excepcional de precedencia o regla extra exige confirmación expresa. La corrección compartida requiere misma causa/evidencia/versiones y casillas de alcance.

**Consecuencias:** resolución auditable, con coste humano declarado. No sustituye identidad autenticada ni prueba automáticamente la veracidad de una referencia aportada. No ejecuta pagos. La mejora adicional prepara borradores por proveedor con preguntas y expedientes; no envía ni aplica decisiones masivas.

**Evidencia:** test_workspace.py comprueba caducidad por cambios, confirmaciones obsoletas, restricciones de PAGAR, conservación selectiva, borrador descargable y auditoría. Tests de corrección no destructiva, CSRF/Host/origen. La demo muestra preguntas aún pendientes tras corregir una lectura.

## ADR-06 · Perfil OCR específico, evaluado y acotado para Lote 2

**Contexto:** los 40 PDFs del segundo lote introducen idiomas, monedas y
formas de manipulación que no deben cambiar el comportamiento ya comprobado
del lote de 500. Forzar OCR a todo encarece y puede reemplazar texto nativo
bueno; aceptar cualquier lectura OCR aumentaría falsos pagos.

**Alternativas:** usar el extractor estándar sin adaptación; mandar los 40
PDFs a un servicio cloud; reentrenar un modelo con 40 ejemplos; o introducir
un perfil local separado con evaluación de etiquetas y abstención.

**Decisión:** última opción. `lote2_ocr_v1` combina PyMuPDF y RapidOCR/ONNX
local como segundo testigo cuando hay defecto crítico; en el modo `defects`
puede recorrer todas las páginas si falta un campo crítico no monetario.
Preserva ambos candidatos y sus coordenadas, y añade parsing de etiquetas
multilingües/ISO. La clave de caché incluye perfil, versión, modo y umbrales.
Las anotaciones/tachones y los conflictos bloquean `PAGAR`; el código de
política sigue siendo el único que decide. La evaluación es una división
retrospectiva agrupada por proveedor; no presenta extracción como una medición
de pago ni como validación privada.

**Consecuencias:** más cobertura local, sin enviar facturas a terceros y sin
regresar Lote 1; a cambio, no se afirma fine-tuning ni generalización universal.
El holdout interno agrupado es pequeño (10 documentos), no es ciego y debe
repetirse ante un lote oculto/nuevo antes de mover umbrales. Los `template_id`
del lote público son derivados de proveedor, no evidencia independiente de
layout. Las monedas no EUR se extraen pero v3 las escala hasta que exista una
política FX versionada.

**Evidencia:** `scripts/evaluate_lote2_ocr.py`, etiquetas/splits versionados y
el informe con 99,0 % exact match macro de campos en el holdout interno
agrupado, 8/10 expedientes con campos de riesgo autoaceptados y correctos
frente a etiqueta, 31/38 de cobertura segura elegible y 31/40 (77,50 %) sobre
el lote completo. La ejecución E2E guarda 19 `PAGAR`, 1 `NO_PAGAR`, 20
`ESCALAR` y auditoría íntegra; no se vende ese reparto como accuracy.
