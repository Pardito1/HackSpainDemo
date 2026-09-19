Histórico de versiones. Las cifras de cada entrada corresponden a la ejecución de esa versión; las vigentes están en el README.

**Actualización 0.9.1:** corregida la lectura de `Importe` / `Importe_Total` y el historial repetitivo, sin borrar auditoría. **207 tests Python y 13 JavaScript superados.** v7 y v8 se leen correctamente; las reglas nuevas del Excel v8 de prueba NO se han implementado ni aplicado al lote real. [Cambios, límites y actualización](RELEASE-v0.9.1.md).

**Ajuste de interfaz UI1:** la ficha muestra solo «Aprobar para pago» y «No pagar», sin solicitar minutos dedicados. Las dudas siguen pendientes de revisión. Excel, ERP y política se eligen desde un único selector; el ERP no requiere archivo y conserva la vista previa antes de aplicar. [Detalle del ajuste](INTERFAZ-v0.9.0-UI1.md).

**Nuevo en 0.9.0:** extracción de importes unidos por OCR corregida; avisos importantes en amarillo; error del ERP persistente y recuperable; percentil y validación de costes corregidos. **197 pruebas Python y 10 JavaScript superadas.** En el lote comprobado: 275 propuestas de pago, 9 no pagar, 216 para revisión y 0 pendientes de procesar. Estos resultados sustituyen las cifras históricas de versiones anteriores; no son una medida de precisión. [Verificación y actualización](RELEASE-v0.9.0.md).

**Una sola Bandeja:** todas las facturas y sus consultas pendientes, con una columna «Fallo detectado» separada de «Qué falta por hacer». Ya no existe la sección «Para Alberto». Las acciones de revisión se conservan al abrir cada expediente. [Cambios y actualización 0.6.0](RELEASE-v0.6.0.md).

**Nuevo en 0.8.0:** marca FactU, hojas del Excel consultables y consultas a proveedores con temas desplegables, borrador editable y confirmación de moneda con evidencia. [Cambios y actualización 0.8.0](RELEASE-v0.8.0.md).

**Desde 0.7.0:** letra más grande, «Datos y actualizaciones» con comparación antes de aplicar, notas opcionales y comprobación de `Pedidos_2025_OLD` como histórico parcial. Una coincidencia de pedido pide revisión; no prueba que esté pagado. [Cambios y actualización 0.7.0](RELEASE-v0.7.0.md).

Histórico 0.5.0: revisiones humanas destacadas e historial que explica quién cambió cada dato, sin selector de lotes ni panel de fuentes/versiones en el expediente. UI1 simplifica las acciones visibles a «Aprobar para pago» y «No pagar». La auditoría completa se conserva aparte. Consulta [cómo actualizar conservando tus datos](RELEASE-v0.5.0.md). Una corrección no es una aprobación y ningún botón mueve dinero.

Novedades 0.4.0: carga/reanudación `lote1` sin copiar identificadores; 500 documentos procesados con ERP HTTP; moneda ausente sin EUR inventado; motivo destacado al principio; auditoría técnica en una pantalla separada. Ver [RELEASE-v0.4.0.md](RELEASE-v0.4.0.md). Los resultados medidos son 273 PAGAR, 9 NO_PAGAR y 218 ESCALAR, con cero documentos pendientes. No son una medición de precisión.

Histórico — corrección 0.3.1: demo y ERP sintéticos coherentes con cuatro casos independientes, prueba de recorrido completo y filtros que explican cuántos resultados se muestran. **115 pruebas Python y 4 JavaScript pasan**. Se mantienen las correcciones 0.3 de OCR, integridad, entradas inválidas y consulta ante instrucciones sospechosas. Consulta [ACTUALIZAR-DEMO.md](../ACTUALIZAR-DEMO.md) si ya tenías la demo antigua. La herramienta sigue siendo local, sin autenticación ni pagos reales; lote 2 y validación privada pendientes.

## Instrucciones de actualización desde versiones antiguas

Para actualizar desde 0.4-0.6, conserva una copia de la carpeta `data` con la app parada. Verifica con `factu --data data verify-audit`, arranca la versión nueva con el mismo estado y vuelve a cargar el Excel original en «Datos y actualizaciones». Compara y aplica para incorporar el histórico, sin repetir OCR. Si vienes de 0.3 o anterior, actualiza primero la extracción siguiendo PROCESAR-500.md. Las respuestas cuyo contexto cambie requieren nueva revisión. No ignores una comprobación de integridad fallida ni borres el historial para hacerla pasar. Pruebas del navegador: `node --test tests/test_frontend.mjs`.
