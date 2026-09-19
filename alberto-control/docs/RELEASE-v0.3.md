# Release 0.3.0 · 19 septiembre 2026

## Correcciones

- Separación del número de factura y fecha contiguos en OCR; validación estricta del identificador y conservación de evidencia.
- Etiquetas OCR correctas en el visor.
- Validación de políticas y Excel dañados con errores comprensibles y sin publicar fuentes inválidas.
- Las instrucciones sospechosas detectadas obligan a ESCALAR y a una revisión humana expresa; permanecen protegidas las comprobaciones críticas.
- Control de integridad ampliado a originales, fuentes, decisiones, manifiestos y registros sellados; bloqueo ante corrupción o exportación con código desactualizado.
- Gestión clara de errores de red, respuestas no JSON e indisponibilidad del ERP.
- Distinción entre copia ERP guardada y conexión en vivo; límites de auditoría visibles.

## Verificación

112 pruebas Python, 4 JavaScript y 34 comprobaciones negativas pasan. Las 500 páginas de expediente responden y la exportación contiene exactamente 500 nombres únicos. Dependencias coherentes; persisten 7 avisos de obsolescencia de dependencias.

El lote inicial reprocesado propone 430 PAGAR, 9 NO_PAGAR y 61 ESCALAR, sin trabajos de procesamiento pendientes. Las consultas humanas no están resueltas automáticamente. Se conservaron originales e historial; no se ejecutaron pagos.

Comprobación ERP independiente, modo normal: 516 registros, 26 páginas, 30 intentos, 3 reintentos, 5,21 segundos; registros iguales a la copia guardada. No se publicó una nueva fuente en esta comprobación.

El segundo lote oficial, la validación humana y la referencia privada del jurado siguen siendo comprobaciones externas pendientes. Ningún resultado de esta release certifica precisión del 100 % ni elegibilidad para el premio. Aplicación local, identidad humana declarada y sin firma externa del historial.

El PDF de arquitectura se actualizó a siete páginas y cinco ADRs, con revisión visual. Las mediciones v0.2 se conservan explícitamente como históricas.
