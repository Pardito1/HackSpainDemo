# Arquitectura implementada · 0.10.0

## Alcance

Herramienta local de conciliación: recibe PDFs y el maestro Excel, consulta el ERP oficial, genera propuestas y permite revisar evidencia. No ejecuta pagos. La persona operadora conserva la decisión de negocio y debe aprobar la política antes de usarla con datos reales.

Flujo: **originales → extracción con evidencia → contexto Excel/ERP → reglas → propuesta/revisión → JSONL**. Cada versión queda ligada al hash del documento, código, extractor, política, maestro y snapshot ERP.

## Componentes

| Componente | Responsabilidad y estado |
|---|---|
| `extract.py` | PyMuPDF por palabras, página y cajas. Despacha perfiles de extracción explícitos; el perfil estándar no recibe cambios por Lote 2. No tiene herramientas de pago ni interpreta instrucciones documentales. |
| `lote2_ocr.py` | Perfil `lote2_ocr_v1`: lectura nativa + RapidOCR/ONNX local como segundo testigo cuando hay defecto crítico; en modo `defects` puede recorrer todas las páginas si falta un campo crítico no monetario. Parsing multilingüe, divisa ISO, anomalías de anotación y evidencia por método. Solo lo puede seleccionar el runner de Lote 2. |
| `modelo.py` | Lectura multimodal opcional si OCR deja campos sin resolver. Validación de candidatos y evidencia, conflictos conservados, reintentos y cortacircuito. No decide ni ejecuta pagos. Sin credenciales no consulta la red. |
| `master.py` / `historical.py` | Adaptadores de proveedores, pedidos actuales e histórico parcial de pedidos. Conservan celdas; no recalculan fórmulas ni toman una coincidencia histórica como pago confirmado. |
| `erp.py` | HTTP real, sesión, ISO-8859-1, XML, paginación y reintentos. Publica únicamente snapshots completos. |
| `policy.py` | Función determinista de hechos y contexto. Todas las comparaciones monetarias usan Decimal. Produce reglas PASS/FAIL/UNKNOWN y preguntas concretas. |
| `db.py` | SQLite WAL, blobs por hash, caché, trabajos, decisiones, revisiones, costes y eventos append-only. |
| `service.py` | Flujo compartido por web/CLI, bloqueo entre procesos, reclamación de trabajo, índice de duplicados y exportación. |
| `workspace.py` | Respuestas humanas, borradores de consulta y cambios de fuentes con impacto, confirmación y caducidad de respuestas. |
| `web.py` | FastAPI/Jinja, interfaz local, CSRF, CSP y validación de Host. Un executor de un worker. |
| `lote1.py` | Carga/reanudación del lote inicial: exige 500 nombres únicos, comprueba originales/Excel/fecha al reanudar, consulta ERP y procesa con OCR. No mezcla la demo ni valida el lote 2. |
| `lote2.py` | Valida exactamente 40 PDFs y las fuentes incrementales, persiste `lote2_ocr_v1`, exige que el bridge contenga la actualización ERP y reanuda de forma idempotente. |
| `scripts/` | Demo sintética separada, benchmark con ERP y comprobación de la entrega. |

Las pantallas muestran procedencia sin ofrecer un razonamiento inventado por un LLM. Una justificación es la lista de controles ejecutados y las fuentes que usaron.

## Estados y transacciones

El trabajo pasa por READY → RUNNING → DONE; los fallos producen RETRY_WAIT y, tras intentos acotados, ERROR. RUNNING conserva un lease de 600 segundos y un token de propietario. Guardar extracción, completar trabajo y registrar evento ocurre en una transacción. Un worker con un token antiguo no puede sobrescribir a su sucesor.

Los documentos pasan por RECEIVED/EXTRACTING/EXTRACTED/WAITING_ERP y DECIDED o HUMAN_REVIEW. Esos estados técnicos son distintos de PAGAR/NO_PAGAR/ESCALAR. La interfaz conserva la bandeja durante un fallo; la exportación falla explícitamente si falta una decisión.

Un bloqueo de workflow en el sistema de archivos impide cambios concurrentes por otra CLI o petición web durante procesado, revisión, cambios de fuentes y exportación. Las lecturas siguen disponibles. Se ha elegido serializar escrituras: no afirmar procesamiento distribuido.

La llegada de un lote invalida las decisiones actuales hasta reconstruir el índice de duplicados. Se mantiene el historial. Ningún lote se finaliza mientras haya trabajos de extracción pendientes: es una barrera conservadora para no omitir duplicados aún ilegibles.

## Identidad y duplicados

El emisor se identifica por NIF, no por el nombre del PDF. Dos filas idénticas de un proveedor no son dos identidades distintas. Filas contradictorias, o relación proveedor/pedido conflictiva entre Excel y ERP, requieren aclaración.

El ERP es la referencia del importe/estado contable. Esa precedencia no permite cambiar silenciosamente la identidad de una factura cuando el maestro discrepa. Un pedido único pagado solo produce NO_PAGAR si la identidad es coherente. Cuando el snapshot tiene historial del mismo pedido, se conservan todas las filas y solo se toma el asiento con fecha más reciente si proveedor, NIF e importe coinciden y la fecha más reciente es única; cualquier ambigüedad escala.

Para documentos que comparten pedido: copias byte a byte conservan un representante canónico y el resto se propone NO_PAGAR; versiones de distinto contenido requieren revisión de ambas. No hay pagos reales y, por tanto, no se afirma exactamente-una-vez bancario.

`Pedidos_2025_OLD` aporta dos pedidos e importes y una nota explícita de archivo parcial. No contiene NIF, número de factura ni estado de pago. Se compara el ID completo de pedido, incluido el año; un importe igual no basta. Una coincidencia requiere ESCALAR salvo evidencia independiente concluyente. Resolverla necesita motivo, evidencia y reconocimiento explícito de la discrepancia, manteniendo los controles críticos. Una fuente antigua aún sin esta lectura se marca pendiente. En las 500 facturas revisadas no hay coincidencias con esos dos pedidos.

## Extracción y confianza

Se conserva valor leído, normalizado, transformaciones y bbox en puntos PDF con origen superior izquierdo. Valores contradictorios no se reducen a uno sin intervención. El score OCR se usa como señal conservadora de calidad (umbral heurístico 0,85), **no como probabilidad calibrada**.

La cadena nativa/OCR no completa los campos usando el maestro. La moneda necesita una mención explícita, con página y coordenadas, o una confirmación humana identificada. Sin moneda se registra MISSING y no se propone PAGAR. No se infiere EUR del idioma, del NIF ni del país; el símbolo $ aislado se considera ambiguo. El parser no tiene entradas por nombre/hash de factura ni una tabla de resultados esperados. En Lote 2, RapidOCR es un segundo testigo con perfil, modo y umbrales incluidos en caché; no convierte una lectura débil o una corrección manuscrita en evidencia suficiente para pago.

El marcador de instrucciones sospechosas obliga a ESCALAR. Alberto puede resolver esa alerta con motivo, evidencia y confirmación expresa, sin saltarse los demás controles. No es un detector universal. La barrera principal sigue siendo arquitectónica: el texto del documento no es código ni política, no se ejecuta y no invoca herramientas externas.

## Integridad reforzada en 0.3

`integrity.py` lee una vista consistente de SQLite y comprueba eventos, manifiestos, originales y blobs, IDs de fuentes por contenido, coherencia entre decisión/payload/contexto/evento, punteros a decisiones y sellos de extracciones/caché e intervenciones nuevas. Los registros antiguos sin sello se anuncian como cobertura parcial. No se vuelve a sellar una alteración detectada: las operaciones y la exportación quedan bloqueadas. El reproceso de la versión anterior conserva eventos, cachés e históricos. No hay firma externa ni protección ante un administrador que reconstruya todas las evidencias locales.

## Humanos, cambios y mejora adicional

La persona confirma lecturas con autor y motivo. La vista previa calcula el resultado y preguntas restantes para cada documento; su token incluye evidencia, revisiones y versiones de lotes. Un cambio posterior invalida la confirmación. La revisión añade un registro; no destruye la lectura original.

La agrupación exige igual identidad, regla, evidencia y versiones. Resuelve correcciones repetidas de lectura con alcance explícito, no cambios masivos de cuenta bancaria ni aprobación ciega de pagos. Si no existen causas compartidas, no inventa grupos.

La respuesta humana de negocio es distinta de la corrección de lectura. Conserva resultado del motor, respuesta, autor declarado, motivo y referencia. La ficha ya no pide minutos; se conservan los declarados anteriormente. PAGAR no omite controles técnicos/bancarios. El anclaje identifica hechos, revisiones, política y código. Si deja de coincidir, vuelve a ESCALAR. Retirar una respuesta deja su motivo en un evento y sella los metadatos de retirada; nunca reactiva una respuesta más antigua.

Actualizar fuentes es parte del flujo principal del reto, no el bonus. Un borrador compara dependencias por factura: pedido ERP; proveedor/pedido/norma y filas históricas coincidentes del maestro; política completa. Primero muestra impacto, después cambia la fuente con guardia de concurrencia. Solo reevalúa afectados y reutiliza OCR; para los demás conserva la decisión y registra por qué sigue siendo aplicable. El índice de duplicados interlote se construye una sola vez por comparación. Un fallo entre commit y reevaluación deja decisiones pendientes, recuperables. La norma textual no modifica código por sí misma.

«Datos y actualizaciones» presenta tres fuentes con fecha registrada y estado, detalles desplegables, vista previa y un historial compacto. Las cantidades de impacto son disjuntas: afectados sin cambio, nuevos ESCALAR y otros cambios; reutilizados aparte. Solo la política o una norma textual modificada requieren confirmación de reglas. Nombre y nota de actualización son opcionales; sin nombre se registra una sesión local sin identificar, nunca una identidad inventada. Esto no relaja los requisitos de autor/motivo/evidencia de una decisión humana.

La mejora adicional propuesta al jurado es la preparación de comunicaciones: preguntas abiertas agrupadas por proveedor, con facturas y referencias, listas para descargar y revisar. No se envían emails, no hay aprobación masiva y no se afirma reducción de tiempo medida todavía. Su consideración como bonus corresponde al jurado.

## Observabilidad y coste

Se registran solicitudes ERP sin credenciales, intentos, estados HTTP, latencias, errores y eventos de publicación; extracción/evaluación por expediente; duración del worker y suma de llamadas externas facturadas. La vista de Alberto muestra el motivo destacado, los datos y la página origen. Los intentos, JSON, hashes y costes se consultan por separado en `/documents/{id}/audit` y `/operations`; la separación de pantallas no es control de acceso.

El benchmark local histórico incluye ERP normal + OCR + reglas, no solo extracción PDF. La memoria máxima es del proceso Python; no mide por separado memoria del ERP. La cifra de workers es uno; ONNX puede usar dos hilos internos. Con el método opcional `modelo` se registran tokens, neuronas y coste según las tarifas configuradas; sin tarifas, cero registrado no demuestra gratuidad.

La extracción de Lote 2 se ha medido contra 40 transcripciones manuales internas revisadas, con holdout retrospectivo agrupado por proveedor: 99,0 % de exact match macro de campos en 10 PDFs y 8/10 expedientes con campos de riesgo autoaceptados y correctos frente a etiqueta. La cobertura segura es 31/38 entre expedientes elegibles y 31/40 (77,50 %) sobre el lote completo. El `template_id` actual deriva del proveedor, por lo que no prueba independencia de layout visual. No es precisión de pagos ni una promesa para formatos no observados; el primer lote no tiene etiquetas equivalentes. La distribución de salidas se reporta separadamente. Sin llamadas externas el coste externo de inferencia es cero; con modelo depende del proveedor y tarifas. Falta imputar hardware y revisión humana. No se ha repetido el benchmark de 500 documentos con el motor integrado 0.10.0.

## Evolución y límites

Para nuevos layouts, ampliar extractores sobre el mismo contrato con evidencia y pruebas negativas. Para CSV/email/imágenes nuevas, incorporar adaptadores explícitos: no están implementados como entradas genéricas. Para v4, revisar y versionar política; extensiones semánticas requieren código/tests.

Para más volumen: medir cuello de botella, mover blobs a almacenamiento de objetos, SQLite a PostgreSQL, jobs a cola durable, workers de extracción independientes y un publicador de decisiones/duplicados transaccional. Mantener un único regulador de consultas al ERP. No multiplicar el tráfico del bridge por el número de workers. Este escalado es un plan, no infraestructura desplegada.

No exponer esta versión fuera de localhost (excepción asumida: la demo del pitch, servida por túnel sobre una copia desechable del estado con datos ya públicos del reto). SSO, RBAC, cifrado, retención, cuotas globales, sandbox de parsers, autenticidad de documentos, firma externa del historial y cumplimiento de licencias son trabajo previo a producción.
