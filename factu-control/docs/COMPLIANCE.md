# Cumplimiento y pendientes · v0.7.0

Actualización vigente 0.7.0: 500 facturas comprobadas, 273 PAGAR / 9 NO_PAGAR / 218 ESCALAR y cero pendientes de proceso. Se incorporan dos pedidos del histórico parcial, sin coincidencias en el lote. 153 pruebas Python y 6 JavaScript pasan. Auditoría válida, 500 páginas de expediente responden correctamente y exportación con 500 registros únicos. PDF de arquitectura actualizado a 0.7.0. Siguen pendientes lote 2 oficial y validación privada; no es una certificación APTO. Las cifras siguientes describen versiones anteriores.

Actualización vigente: 500 facturas procesadas con ERP y OCR habilitado; 273 PAGAR, 9 NO_PAGAR, 218 ESCALAR, cero pendientes. No se asume EUR, motivo arriba y auditoría separada. 127 pruebas Python y 4 JavaScript pasan; plan PDF 0.4.0 de cuatro páginas. Sigue pendiente el lote 2 oficial y la validación privada. Las cifras y descripciones de las versiones anteriores se conservan debajo como histórico, no como resultados actuales.

## Histórico de versiones anteriores

Actualización 0.3.1: corregido el generador de demo, ampliado su ERP a cuatro pedidos y aclarados los filtros de la bandeja. 115 pruebas Python y 4 JavaScript pasan. El nuevo recorrido completo verifica cuatro casos sintéticos separados, incluida la instrucción engañosa como única causa de una consulta. Las cifras del lote oficial en el párrafo y la tabla siguientes proceden de la verificación 0.3; no son una ejecución nueva del lote ni una certificación de precisión.

Correcciones verificadas: campo OCR contiguo, etiquetas OCR, errores de Excel/JSON, errores de conexión del navegador y comprobación de integridad ampliada. 112 tests Python y 4 JavaScript pasan. Las 500 facturas se han reprocesado: 430 propuestas de pago, 9 negativas y 61 consultas; no es una medida de precisión. Las cinco facturas con instrucciones sospechosas detectadas quedan en ESCALAR. Originales e intervenciones humanas conservados con copia de seguridad previa.

| Requisito | Estado comprobado |
|---|---|
| 500 facturas + Excel + ERP real | Implementado y probado sobre los materiales aportados; 500/500 hashes coincidentes |
| PAGAR / NO_PAGAR / ESCALAR | Motor determinista con política de equipo y respuesta humana explícita; no ejecuta pagos |
| Preguntar ante duda | Bandeja de consultas, preguntas, evidencia, respuesta con motivo y caducidad si cambian hechos |
| Trazabilidad / observabilidad (20) | Original, bbox/celda, reglas, versiones, historial, intentos, errores, tiempos y costes |
| Producto / arquitectura / ADRs (35) | App local, documentación de lo implementado y cinco ADRs en albertitos_plan.pdf |
| Escala / coste (25) | Benchmark extremo a extremo con ERP normal, hardware/RSS, fórmula editable de coste y límites; un worker real |
| Resiliencia (10) | Persistencia, reintentos, leases, idempotencia, recuperación y exportación bloqueada ante pendientes |
| Ejecución (10) | Interfaz editorial orientada a tareas, español claro, filtros, consulta, evidencia y cambios |
| Cambio de dato en defensa | Vista previa de impacto y reproceso selectivo sin OCR; pruebas de afectados/no afectados y respuesta obsoleta |
| +40 facturas oficiales | Pendiente de recibir/procesar. Existe prueba sintética de 40 documentos, no es el lote oficial |
| Bonus (+10) | Borradores de consulta por proveedor implementados; no cuentan como aceptación del jurado ni ahorro medido |
| Dos JSONL + plan en repo separado | Exportador y validador disponibles. Falta lote 2; no se ha publicado ni presentado una entrega |
| APTO / accuracy | Desconocidos: solo el verificador privado puede acreditar elegibilidad; falta muestra etiquetada independiente |

## Preparación de la defensa

No confundir cobertura (500 decisiones) con precisión; automatización con acierto; 0 € de proveedores con coste total cero; respuesta humana declarada con identidad autenticada; cadena de hashes local con almacenamiento inmutable invulnerable.

La recuperación demostrada corresponde al ERP y al worker/OCR. No usamos proveedor LLM: no atribuimos al producto un failover generativo inexistente. Explicarlo al jurado y mostrar una caída real del conector o una interrupción del worker.

Esta versión es local, sin roles/SSO ni endurecimiento para datos bancarios reales. No exponerla a Internet.

## Lista antes de enviar

1. Validar políticas y revisar una muestra independiente más escalados críticos.
2. Incorporar lote 2/ERP/norma con versiones, regresiones y auditoría del impacto.
3. Exportar ambos lotes; actualizar plan con mediciones finales.
4. Ejecutar validate_submission.py. Solo comprueba estructura/cobertura; no referencia privada.
5. Publicar por decisión del equipo un repositorio de resultados separado con exactamente los tres archivos y compartir teamId/URL a tiempo.
