# FactU 0.9.1 · Columnas y actividad comprensibles

- `Pedidos_2026` y `Pedidos_2025_OLD` resuelven columnas por encabezado. `Importe` e `Importe_Total` son alias explícitos. Se conservan las coordenadas reales y se rechazan encabezados ambiguos.
- v7 comprobado: 14 hojas, 516 pedidos actuales y 2 históricos. v8 de prueba: 4 hojas, 121 actuales y 5 históricos. No se modificó ninguno de los Excel.
- Un histórico puede incluir proveedor y estado, pero sigue siendo parcial. `CERRADO` no se interpreta como pago confirmado.
- La actividad agrupa verificaciones automáticas consecutivas con los mismos datos, incidencias y resultado. El desplegable conserva las fechas y explica los cambios de aplicación/fuentes. No borra decisiones ni confunde una corrección con una aprobación.
- Se mantienen los cambios UI1: sin botón «Pedir información» ni minutos en la factura; ERP disponible en el selector de fuentes; comparación antes de aplicar.

## Validación

207 tests Python y 13 JavaScript superados. Siete avisos de deprecación de dependencias. Verificado con los Excel reales v7/v8; los 500 JSONL coinciden con los nombres originales, no hay duplicados ni pendientes y la auditoría es válida. Distribución: 275 PAGAR, 9 NO_PAGAR y 216 ESCALAR. Repetir la evaluación con el mismo contexto no añade decisiones; no se ha repetido OCR.

## Límite importante del Excel v8

Leer una nueva estructura no equivale a implementar sus reglas. Este archivo de prueba cambia la norma e introduce plazos y bloqueo de nuevos proveedores. No se ha aplicado al lote real ni se ha confirmado automáticamente su correspondencia con el motor. Hay que definir desde qué fecha corren los plazos y qué historial acredita un proveedor conocido, implementar y probar esa política antes de activarla. La importación conserva el aviso de norma modificada.

## Actualizar una instalación existente

1. Detén la app y conserva una copia de toda la carpeta de estado.
2. Instala esta versión sin mezclar sus archivos con otra.
3. Activa el entorno virtual; utiliza la misma ruta de estado en todos los comandos.
4. Ejecuta `python -m factu --data RUTA_ESTADO verify-audit`.
5. Ejecuta `python -m factu --data RUTA_ESTADO evaluate ID_DEL_LOTE` (en esta versión reevalúa todos los lotes del estado).
6. Arranca con `python -m factu --data RUTA_ESTADO serve --port 8089`.

La reevaluación no aprueba pagos. Una respuesta humana cuyo fundamento cambie puede requerir nueva confirmación. Los originales y la auditoría no se eliminan. Para una instalación nueva, sigue PROCESAR-500.md; subir el código no crea por sí solo el estado local.

El segundo lote oficial no está disponible en los materiales revisados: no se genera un resultado falso o vacío. La entrega del concurso sigue incompleta hasta procesar ese lote y validar ambos JSONL.
