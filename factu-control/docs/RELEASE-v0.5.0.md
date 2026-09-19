# v0.5.0 · Una pantalla para Alberto

## Qué cambia

- El historial dice «Marta corrigió el IBAN», «Comprobaciones actualizadas» o «Alberto aprobó para pago». No muestra identificadores internos como #2 o #4. Los resultados anteriores no se reescriben como si ya hubieran sido aprobados.
- La última corrección aparece al principio: autor, fecha, valor anterior, valor confirmado y motivo. Cada campo revisado también lo muestra de forma destacada.
- Tres acciones visibles: Aprobar para pago, No pagar y Pedir información. Primero se elige, después se escribe el motivo y la evidencia, se comprueba y se confirma. Cambiar la acción invalida la vista previa anterior.
- El botón de aprobación está bloqueado si quedan controles esenciales sin resolver. El servidor vuelve a comprobarlo: no basta con cambiar el botón en el navegador. Las discrepancias de negocio permitidas requieren confirmación expresa.
- Aprobar solo registra una decisión; no realiza transferencias ni modifica el ERP. La sesión local no autentica al revisor.
- Quitados el selector de lote de la bandeja y «Fuentes y versiones» del expediente normal. Los lotes siguen existiendo internamente para no mezclar entregas; no se borran datos. Los enlaces que ya seleccionaban un lote conservan su contexto. La bandeja raíz `/` reúne todos los documentos.
- Fuentes, hashes, versiones y eventos completos siguen en el área técnica y en la auditoría de cada factura.

## Actualizar sin perder tus revisiones

1. Para la aplicación anterior con Ctrl+C. Conserva una copia de su carpeta de estado completa (por defecto `data`). **No borres ni sustituyas tu base de datos con una demo.**
2. Descomprime esta versión en otra carpeta. Instala siguiendo el README, desde esa nueva carpeta. Reutiliza la ruta absoluta del estado anterior.
3. Ejecuta los comandos siguientes, sustituyendo `RUTA_ABSOLUTA_ESTADO` y `ID_LOTE` por tus valores. Son válidos en macOS/Linux y en Windows dentro de WSL2, con el entorno virtual activado:

```bash
python -m factu --data "RUTA_ABSOLUTA_ESTADO" verify-audit
python -m factu --data "RUTA_ABSOLUTA_ESTADO" batches
python -m factu --data "RUTA_ABSOLUTA_ESTADO" evaluate ID_LOTE
python -m factu --data "RUTA_ABSOLUTA_ESTADO" serve --port 8089
```

Abre http://127.0.0.1:8089/ y recarga la página. `evaluate` revisa todos los lotes para mantener coherentes los duplicados entre ellos. No repite OCR ni borra correcciones. Si falla la comprobación de integridad, detente: no borres el historial. El cambio de versión puede requerir revalidar respuestas de aprobación anteriores; se conservan y no se renuevan sin una persona.

Si vienes de una versión anterior a 0.4.0, sigue primero PROCESAR-500.md para actualizar la extracción de moneda y cargar el lote oficial; este ZIP no incluye los PDFs oficiales ni tu base de datos local.

## Pruebas y límites

Pruebas automatizadas de motor, web, revisión, protección de pagos y auditoría incluidas en `tests/`. También se ha recorrido en navegador una factura sintética: corregir IBAN, mantener la advertencia, denegar aprobación sin confirmarla, cambiar de decisión, confirmar y comprobar el historial. No se han aprobado facturas oficiales durante esa prueba.

El PDF de arquitectura incluido describe la base 0.4.0. Esta versión no cambia el contrato de entrega ni las reglas de negocio; esta nota documenta el cambio de presentación y el control compartido de aprobación. Actualizad el plan final con v4/lote 2 y vuestras decisiones reales antes de entregarlo al jurado. No se garantiza el resultado del verificador privado.
