# v0.6.0 · Todo en Bandeja

- Columna nueva «Fallo detectado», calculada a partir de las comprobaciones registradas, sin volver a leer el PDF ni llamar a una IA. No se confunde el diagnóstico con la pregunta al usuario.
- Una factura no comprobada dice «Comprobación pendiente», nunca «Sin incidencias». Las facturas sin problemas detectados se indican como tales, sin prometer una precisión no medida.
- Los problemas adicionales se despliegan en la misma celda. Las discrepancias revisadas por una persona siguen visibles con esa indicación.
- «Para Alberto» desaparece del menú y de la cabecera. En Bandeja aparecen «Todas» y «Pendientes de revisión», el contador de consultas y el acceso a la primera pendiente. Abrir el expediente mantiene correcciones, evidencia, historial y decisiones humanas con doble confirmación.
- Las demos de desarrollo se mantienen separadas del estado de trabajo oficial. El ZIP no contiene bases de datos ni facturas de demostración cargadas. No se filtra automáticamente por nombres como «demo»: ocultar documentos por una palabra dentro de un archivo podría esconder facturas legítimas.
- No cambian las reglas de pago, el formato JSONL ni la auditoría. El PDF de arquitectura describe la base 0.4.0; las notas 0.5.0 y 0.6.0 documentan los cambios de interfaz. Actualizad el PDF final con vuestra solución y lote 2 antes de entregarlo.

## Actualización

Para la instancia anterior con Ctrl+C, copia su carpeta de estado como respaldo y usa esta versión con la carpeta que contiene las facturas oficiales. No uses `demo-state`. Si ya importaste las 500, no las vuelvas a importar ni borres el estado: conserva sus identificadores y revisiones.

Desde esta carpeta, con el entorno virtual activado (Mac/Linux o Windows con WSL2):

```bash
python -m factu --data "RUTA_ESTADO_OFICIAL" verify-audit
python -m factu --data "RUTA_ESTADO_OFICIAL" batches
python -m factu --data "RUTA_ESTADO_OFICIAL" evaluate ID_LOTE
python -m factu --data "RUTA_ESTADO_OFICIAL" serve --port 8089
```

Abre http://127.0.0.1:8089/. El estado se conserva; la nueva versión de código puede exigir revalidar aprobaciones humanas previas, nunca las renueva por su cuenta. No sigas si falla la integridad. Para la primera carga, utiliza PROCESAR-500.md.

Para retirar una instancia antigua de demo sin perder una revisión de prueba, para su servidor y conserva `demo-state` aparte. No borres filas de SQLite ni alteres eventos: el historial es inmutable. Los scripts de demo se pueden seguir usando en un directorio de pruebas aislado, nunca como origen de la Bandeja habitual.
