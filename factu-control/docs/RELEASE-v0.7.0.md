# v0.7.0 · Datos y actualizaciones

## Qué cambia para Alberto

- Texto principal de 17 px y controles de 16 px. Textos secundarios y tabla ampliados, sin reducirlos para encajar.
- Tres tarjetas de fuentes con fecha registrada, estado y detalles desplegables. La fecha no promete que la información siga vigente en un sistema externo.
- Formulario con solo la fuente y el archivo. Nombre y nota opcionales. Sin autenticación no se inventa un usuario: se registra «Sesión local (sin identificar)».
- Confirmación de revisión de reglas solo al cargar una política o al detectar que el Excel también cambia la norma. La comprobación del servidor se mantiene aunque se manipule la interfaz.
- Botón independiente de consulta del ERP. Comparar no modifica las fuentes activas; aplicar exige una previsualización vigente.
- Resumen sin doble conteo: dentro de las facturas afectadas, resultado igual / pasan a revisión / otros cambios. Las decisiones que se reutilizan se cuentan aparte.
- Historial compacto. Hashes, celdas, código y materiales del concurso permanecen en el área técnica.
- La comparación prepara una única búsqueda de duplicados para todos los documentos, incluidos otros lotes. Evita recorrer y releer el lote completo por cada factura.

## Histórico: decisión y límites

Se incorpora `Pedidos_2025_OLD` sin modificar el Excel. El archivo adjunto contiene dos pedidos (`PO-2025-0812` y `PO-2025-0977`) y una nota de archivo parcial. No hay clientes/proveedores, números de factura ni estados de pago históricos.

Solo una coincidencia exacta de pedido normalizado genera una incidencia `historical_order`. No se elimina el año ni se comparan importes sueltos para declarar duplicados. Una nota no es un pedido; las fórmulas no se ejecutan. Cada registro conserva hoja, fila y celdas.

La coincidencia lleva a ESCALAR, salvo evidencia independiente concluyente como un pago confirmado en el ERP. Alberto puede resolver una coincidencia histórica con motivo, evidencia y reconocimiento explícito de la discrepancia; los controles críticos de identidad, cuenta, importe y pagos previos permanecen. La ausencia de coincidencia solo significa que no figura en el archivo parcial, no que se haya descartado todo el pasado.

El histórico participa en el análisis de impacto y en la evidencia que vincula una respuesta humana. Un cambio en un pedido distinto no invalida decisiones ajenas; uno relacionado se reevalúa sin repetir OCR.

## Actualizar un estado existente

1. Conserva la carpeta `--data` anterior. No la borres ni mezcles con datos de demo.
2. Arranca esta versión con esa misma carpeta y abre «Datos y actualizaciones».
3. Vuelve a cargar el Excel original. Pulsa «Ver facturas afectadas», revisa y aplica.
4. La nueva lectura incorpora el histórico; la fuente y decisiones anteriores permanecen registradas. Un cambio de código puede requerir reevaluar todas las facturas, pero no repetir su lectura.

Una fuente antigua que contenga la hoja histórica pero aún no la haya incorporado se marca pendiente, nunca como comprobada. Si cambias código, revalida resultados antes de exportarlos. No ejecutes la demo para actualizar una base de 500 facturas.

## Entrega del concurso

El ZIP es de código y documentación, no incluye estado, facturas originales ni credenciales. El PDF de arquitectura está actualizado a 0.7.0 e incluye el histórico parcial, la nueva interfaz y cinco ADRs. Completad la validación y las decisiones del lote 2 antes del concurso. Esta versión no certifica APTO frente a la referencia privada.
