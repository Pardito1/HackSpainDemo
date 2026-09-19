# Análisis del reto

Reconocimiento del entorno realizado el viernes 19/09/2026 antes de tocar código del producto. Recoge las trampas medidas del reto (ERP `ORA-00600` determinista cada 10 peticiones, caracteres invisibles `U+200B` dentro de los datos, filas duplicadas del maestro) y el inventario de instrucciones inyectadas en los PDFs de las 500 facturas.

Estos hallazgos alimentaron las reglas explícitas y los tests del producto que vive en `../factu-control/`; se dejan aquí como evidencia de que las decisiones del código responden a observación medida y no a supuestos.

- [`HALLAZGOS.md`](HALLAZGOS.md): trampas del entorno.
- [`INYECCIONES.md`](INYECCIONES.md): mapa de prompt-injections detectadas en los PDFs.
