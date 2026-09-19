# FactU 0.8.0

## Qué cambia

- La web se llama FactU. El estado ESCALAR se presenta como «Requiere revisión»; los JSONL conservan PAGAR, NO_PAGAR y ESCALAR.
- Se retiran de la interfaz habitual las etiquetas de sesión, versión, concurso y estado local de la cabecera. No se añade autenticación: la aplicación sigue siendo local y el nombre del revisor es declarado.
- En Datos y actualizaciones → Ver detalles del Excel → Qué hojas utilizamos, cada hoja se puede abrir. Las demás están en «Otras hojas conservadas». El visor muestra 50 filas y hasta 8 columnas por página; no ejecuta fórmulas ni enlaces. Se descarga el Excel original exacto, comprobando su integridad.
- Consultas a proveedores sustituye a En común: resumen, búsqueda sin tildes, filtro por prioridad y un proveedor abierto a la vez. Dentro: temas, expedientes y borrador editable. No se envían correos ni se guarda automáticamente el texto editado; se puede copiar o descargar mientras la página permanezca abierta.
- La prioridad significa volumen, no vencimiento ni riesgo: alta desde 10 facturas. Los importes conocidos se separan por moneda; los desconocidos se indican, no se convierten a euros ni a cero.
- Solo se incluyen preguntas externas de una lista explícita: moneda, referencia, fecha e importes. Las instrucciones sospechosas, identidad incierta y lectura incompleta requieren primero revisión interna. ERP, cuenta bancaria, fuentes y duplicados no se convierten en preguntas al proveedor.
- Una respuesta verificada permite confirmar la moneda en facturas seleccionadas. Autor, respuesta y referencia son obligatorios. Antes de guardar se muestra el valor actual, el propuesto, la evidencia y el resultado previsto. No hay selección automática, cambio de IBAN compartido ni aprobación de pagos en bloque.
- Se conserva Pedidos_2025_OLD como archivo histórico parcial. Una coincidencia pide revisión; no demuestra un pago anterior.

## Actualizar sin perder el trabajo

1. Detén la app con Ctrl+C en su terminal.
2. Conserva una copia de tu carpeta de datos completa (base de datos y originales). No borres esa carpeta ni la subas a GitHub.
3. Sustituye el código por esta versión y vuelve a instalar sus dependencias si procede.
4. Arranca usando **la misma ruta de datos**. El comando sigue siendo `python -m factu`; el paquete no se ha renombrado para mantener compatibilidad.
5. Como cambia la versión del código, vuelve a comprobar las decisiones antes de exportar. En la CLI: `python -m factu --data RUTA_DE_DATOS evaluate ID_DEL_LOTE` (el ID aparece en la URL de la bandeja, después de `batch=`). Las lecturas y los originales se reutilizan. Si el código o la evidencia cambia, una aprobación humana anterior puede pedir confirmación de nuevo.

En macOS usa el Python de tu entorno virtual. En Windows esta entrega utiliza WSL2: el bloqueo de procesos depende de `fcntl`; no se presenta como compatible con PowerShell nativo.

## Límites que no se deben ocultar

La aplicación no autentica usuarios, no verifica automáticamente que un correo sea genuino, no envía mensajes y no ejecuta pagos. La persona debe verificar la procedencia y alcance de una respuesta antes de confirmarla. El visor conserva valores y fórmulas, no reproduce el diseño de Excel ni calcula sus fórmulas. Los límites de tamaño del visor son 20.000 filas y 200 columnas por hoja; el original sigue descargable.

Las pruebas de formularios se realizan en una copia aislada: no introducen confirmaciones ficticias en las 500 facturas reales. Los resultados del verificador privado y el lote oficial adicional siguen pendientes de validación externa.
