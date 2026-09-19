# FactU · Ajuste de interfaz UI1

19 de septiembre de 2026. Ajuste sobre 0.9.0: no cambia el motor ni las decisiones existentes.

## Ficha de factura

- Solo dos acciones de decisión: «Aprobar para pago» y «No pagar».
- Retirados «Pedir información» y «Minutos dedicados».
- Si falta aclarar un dato, la factura continúa pendiente de revisión sin pulsar ninguna acción. «Consultas a proveedores» sigue disponible para preparar un borrador.
- Se mantienen nombre, motivo, evidencia, comprobación previa y confirmación. Aprobar sigue bloqueado mientras falten comprobaciones necesarias. Ningún botón mueve dinero.
- Las decisiones y los tiempos registrados anteriormente no se borran. La API conserva la compatibilidad con el campo opcional de tiempo; la ficha no lo envía. Su valor por defecto cero no es una medición del trabajo humano.

## Datos y actualizaciones

«Fuente que quieres actualizar» reúne Excel, ERP y política. Al elegir ERP no se pide archivo ni confirmación de reglas: se consulta la contabilidad y se abre el resumen de impacto. Es necesario pulsar «Aplicar actualización» después para cambiar la fuente activa. Al volver a Excel o política, reaparecen los campos correspondientes. Si todavía no existe una consulta inicial al ERP, se conserva el botón de primera consulta.

## Actualización

Los cambios están aplicados en la carpeta de esta versión. Recarga la página para obtener las plantillas y el JavaScript nuevos. Para otro equipo, utiliza el ZIP UI1 con su propia carpeta de datos conservada; el ZIP contiene código, documentación y pruebas, no bases de datos ni materiales oficiales.

## Verificación realizada

- 201 pruebas Python y 13 pruebas JavaScript superadas. Persisten avisos de obsolescencia de dependencias; no fallos de pruebas.
- Navegador: dos acciones de decisión, formulario sin minutos, campos correctos al alternar Excel/ERP/política y ningún error de consola durante el recorrido.
- Consulta HTTP al ERP desde una copia aislada de los 500 expedientes: vista previa generada, 11 facturas para comprobar de nuevo conservando su resultado y 489 sin reevaluación. No se aplicó la actualización a las facturas del usuario.
- Las pruebas automatizadas verifican por separado la aplicación explícita de una actualización y la confirmación humana sin enviar tiempo, usando datos sintéticos de pruebas.
