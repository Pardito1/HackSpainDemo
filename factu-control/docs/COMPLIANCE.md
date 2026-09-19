# Cumplimiento y pendientes · v0.10.0

## Estado actual · Lote 2 público

El runner dedicado valida los 40 PDFs oficiales, el Excel v7, los dos CSV
incrementales y la actualización ERP antes de publicar resultados. La ejecución
end-to-end contra el bridge oficial produjo 24 `PAGAR`, 1 `NO_PAGAR` y 15
`ESCALAR`, con auditoría válida. El resultado es un corte local de fuentes,
política v3 y fecha `2026-09-20`; no es una certificación APTO ni precisión
frente a la referencia privada.

El perfil `lote2_ocr_v1` está aislado del lote de 500. Se evaluó como perfil de
extracción completo frente a transcripciones manuales internas revisadas: 99,0
% de exact match macro de campos en un holdout interno agrupado de 10
documentos y 8/10 expedientes con campos de riesgo autoaceptados y correctos
frente a etiqueta. Es una división retrospectiva por proveedor, no validación
privada ni evidencia independiente de layout visual. No se vende como accuracy
de pagos ni de RapidOCR aislado. Moneda ausente/ambigua, no-EUR sin FX
trazable, inconsistencias, anotaciones y texto no fiable se escalan.

**345 pruebas Python y 15 de Node pasan** (dos avisos de deprecación de dependencias, medido 2026-09-20 en M1). Las cifras y descripciones que siguen son históricas de versiones anteriores.

## Histórico de versiones anteriores

Actualización 0.3.1 (histórico): corregido el generador de demo, ampliado su ERP a cuatro pedidos y aclarados los filtros de la bandeja. 115 pruebas Python y 4 JavaScript pasan. El nuevo recorrido completo verifica cuatro casos sintéticos separados, incluida la instrucción engañosa como única causa de una consulta. Las cifras del lote oficial en el párrafo y la tabla siguientes proceden de la verificación 0.3; no son una ejecución nueva del lote ni una certificación de precisión.

Correcciones verificadas (histórico): campo OCR contiguo, etiquetas OCR, errores de Excel/JSON, errores de conexión del navegador y comprobación de integridad ampliada. 112 tests Python y 4 JavaScript pasan. Las 500 facturas se han reprocesado: 430 propuestas de pago, 9 negativas y 61 consultas; no es una medida de precisión. Las cinco facturas con instrucciones sospechosas detectadas quedan en ESCALAR. Originales e intervenciones humanas conservados con copia de seguridad previa.

| Requisito | Estado comprobado |
|---|---|
| 500 facturas + Excel + ERP real | Implementado y probado sobre los materiales aportados; 500/500 hashes coincidentes |
| PAGAR / NO_PAGAR / ESCALAR | Motor determinista con política de equipo y respuesta humana explícita; no ejecuta pagos |
| Preguntar ante duda | Bandeja de consultas, preguntas, evidencia, respuesta con motivo y caducidad si cambian hechos |
| Trazabilidad / observabilidad (20) | Original, bbox/celda, reglas, versiones, historial, intentos, errores, tiempos y costes |
| Producto / arquitectura / ADRs (35) | App local, arquitectura y seis ADRs en Markdown; `docs/albertitos_plan.pdf` v0.10.0 ya está generado y debe conservarse junto al código que lo reproduce |
| Escala / coste (25) | Benchmark extremo a extremo con ERP normal, hardware/RSS, fórmula editable de coste y límites; un worker real |
| Resiliencia (10) | Persistencia, reintentos, leases, idempotencia, recuperación y exportación bloqueada ante pendientes |
| Ejecución (10) | Interfaz editorial orientada a tareas, español claro, filtros, consulta, evidencia y cambios |
| Cambio de dato en defensa | Vista previa de impacto y reproceso selectivo sin OCR; pruebas de afectados/no afectados y respuesta obsoleta |
| +40 facturas oficiales | Implementado: runner de 40 PDFs, perfil OCR separado, fuentes incrementales versionadas y ejecución contra bridge oficial |
| Bonus (+10) | Borradores de consulta por proveedor implementados; no cuentan como aceptación del jurado ni ahorro medido |
| Dos JSONL + plan en repo separado | Exportador y validador disponibles; exportar desde el estado auditado e incluir el PDF v0.10.0 ya generado |
| APTO / accuracy | APTO sigue desconocido: solo el verificador privado puede acreditarlo. Hay métrica interna de extracción Lote 2, no precisión de pagos |

## Preparación de la defensa

No confundir cobertura (500 decisiones) con precisión; automatización con acierto; 0 € de proveedores con coste total cero; respuesta humana declarada con identidad autenticada; cadena de hashes local con almacenamiento inmutable invulnerable.

La recuperación demostrada corresponde al ERP y al worker/OCR. No usamos proveedor LLM: no atribuimos al producto un failover generativo inexistente. Explicarlo al jurado y mostrar una caída real del conector o una interrupción del worker.

Esta versión es local, sin roles/SSO ni endurecimiento para datos bancarios reales. No exponerla a Internet. La demo pública del pitch es la excepción declarada: copia desechable del estado, datos del reto ya públicos, sin acceso a la entrega ni a credenciales.

## Lista antes de enviar

1. Validar políticas y revisar una muestra independiente más escalados críticos.
2. Revisar todos los escalados críticos del Lote 2 y una muestra independiente de `PAGAR` antes de exportar.
3. Exportar ambos lotes e incluir `albertitos_plan.pdf` v0.10.0 ya regenerado (solo se regenera si cambian código, métricas o ADRs).
4. Ejecutar validate_submission.py. Solo comprueba estructura/cobertura; no referencia privada.
5. Publicar por decisión del equipo un repositorio de resultados separado con exactamente los tres archivos y compartir teamId/URL a tiempo.
