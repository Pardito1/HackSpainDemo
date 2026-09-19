# FactU 0.9.2 · Integración del equipo

Integración del código local 0.9.1 sobre `main` 5b3fe97. Se respeta el cambio de nombre del equipo: carpeta `factu-control`, paquete/CLI `factu`.

## Qué se conserva

- Interfaz FactU, motivos destacados, Bandeja unificada con fallo detectado, historial resumido y auditoría separada.
- Datos y actualizaciones con Excel, ERP y política; consulta de hojas, alias Importe/Importe_Total e histórico parcial.
- Consultas a proveedores con borrador y respuestas verificadas; sin envío automático ni aprobación masiva.
- Lectura opcional con modelo, validación y degradación ante fallos añadidas por el equipo. No se fuerza moneda EUR ni se permite que un modelo decida pagos.
- Ordenación por proveedor e importe, métricas OCR/texto, saludo según la hora y retirada auditada de respuestas. Se elimina el selector duplicado de estados: tarjetas y enlaces filtran la Bandeja.
- Todo el trabajo remoto ajeno a la app: materiales, prototipo, pruebas y referencias.

## Ajustes de integración

La retirada de la última respuesta vuelve al motor sin reactivar respuestas antiguas. Una instalación con `alberto.sqlite3` se reutiliza sin abrir silenciosamente una base vacía; dos bases en la misma carpeta requieren elección explícita. El percentil 95 utiliza rango más próximo. Se muestran las evidencias del modelo en el expediente. La versión del extractor es `native-rapidocr-modelo-7`, para no reutilizar lecturas de otro contrato como si fueran actuales.

## Verificaciones

- `python -m pytest -q` en `factu-control`: **251 aprobadas**; avisos de deprecación de dependencias, sin errores.
- `node --test tests/test_frontend.mjs`: **13 aprobadas**.
- Incluye pruebas de demo mediante HTTP real en localhost, interrupciones del ERP, recuperación, integridad, revisiones, moneda ausente, reglas y fallos simulados del proveedor de modelo. No se han hecho llamadas facturables a un LLM.
- Las pruebas del prototipo raíz `tests/` son independientes: 51 aprobadas y 3 fallos en `test_robustez.py`, porque `pipeline/extraccion.py` sigue siendo un stub. Los mismos tres fallos se han reproducido en un checkout limpio de `main` 5b3fe97. Ese motor no se importa desde FactU y no se sustituye en esta integración. No se afirma que todo el repositorio esté libre de fallos.

## Antes de usar datos anteriores

Detén la app y conserva una copia de la carpeta de estado. Arranca con esa misma ruta `--data`; verifica la auditoría. Vuelve a importar/comparar el Excel original si faltaba el histórico. Para incorporar el lector integrado utiliza `reextract ID_LOTE` y después `process ID_LOTE`, con el ERP disponible. Se conserva el historial; las respuestas cuyo fundamento cambie requieren nueva revisión. No borres registros ni ignores una auditoría fallida.

## Pendiente (no ocultado)

No se han implementado las reglas nuevas del Excel v8 de prueba. Marcar su casilla de revisión no traduce texto a reglas: solo debe confirmarse tras verificar que la política ejecutable corresponde. Sigue faltando el segundo lote oficial, por lo que no se crea un `outcomes_lote2.jsonl` vacío o ficticio. La carpeta `entrega-parcial-v0.9.1` conserva una ejecución anterior de 500 resultados y su plan, no una certificación del motor integrado. No se han reprocesado los 500 originales en esta integración.

La aplicación es local y sin autenticación de producción; publicar código en GitHub no despliega una web pública ni sube el estado local.
