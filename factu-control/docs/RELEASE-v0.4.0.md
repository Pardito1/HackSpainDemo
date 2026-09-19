# Cambios comprobados · 0.4.0

## Para Alberto

- Motivo específico destacado al principio del expediente, con siguiente acción. Las instrucciones sospechosas tienen prioridad visual y no se obedecen.
- JSON, hashes, eventos internos y tiempos fuera del expediente de usuario. Se conservan en `/documents/{id}/audit`, `/sources/audit` y `/operations`. Separación visual, no autenticación ni roles de seguridad.
- Moneda solo leída cuando aparece en el documento y tiene evidencia. Ausencia, contradicción o símbolo `$` ambiguo requieren aclaración. Una confirmación humana conserva el original y se identifica como tal.
- Resumen con facturas comprobadas en lugar del coste externo, que sigue disponible en el área técnica. Cero gasto de API no significa cero coste total.

## Carga del lote real

Nuevo comando `python -m factu --data estado-500-v04 lote1 ...`. Exige 500 PDFs, comprueba el manifiesto al reanudar, consulta el ERP y utiliza OCR. Rechaza la mezcla con la demo. Instrucciones en `PROCESAR-500.md`.

Prueba sobre los archivos oficiales que coinciden con los adjuntos: 500 PDFs; ERP HTTP normal con 516 asientos y 3 reintentos en la carga. Se han obtenido 273 PAGAR, 9 NO_PAGAR y 218 ESCALAR, sin pendientes de proceso. Se conservan propuestas y consultas; no hay pagos ejecutados ni aprobaciones humanas fabricadas.

127 pruebas Python y 4 JavaScript pasan. Se comprueban moneda ausente/contradictoria, evidencia, confirmación humana, separación de pantallas, rechazo de demo y reanudación sin duplicados; además de las regresiones anteriores. Hay siete avisos de deprecación de dependencias, no fallos de las pruebas.

Los documentos `RELEASE-v0.3*.md` y benchmarks v0.2/v0.3 son históricos; no describen la distribución de esta ejecución. El cambio de moneda es deliberadamente conservador: puede aumentar las consultas. No se ha medido precisión con etiquetas independientes ni ejecutado el validador privado; el lote 2 oficial sigue pendiente de incorporación.

Compatibilidad: probado en macOS arm64/Python 3.12. Windows requiere WSL2 por el bloqueo `fcntl`; no se ha validado Windows nativo. No exponer la app a Internet.
