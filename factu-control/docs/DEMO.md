# Defensa de 10 minutos · v0.2

Frase de apertura: **«Alberto no necesita otra caja negra. Necesita saber qué está comprobado, qué falta y qué cambia cuando responde.»**

## 0:00–2:00 · Producto

Bandeja real: 500 facturas, propuestas y preguntas diferenciadas. Abrir un ESCALAR; localizar la evidencia en el PDF. Mostrar la pregunta, no un porcentaje de confianza inventado. En «En común», descargar un borrador agrupado por proveedor: la mejora prepara el trabajo de comunicación, no manda emails ni autoriza pagos.

## 2:00–4:00 · Arquitectura y criterio

Original → extracción con procedencia → Excel/ERP versionados → controles → propuesta o pregunta → respuesta humana trazada.
Apoyarse en los cinco ADRs del plan. Explicar que el OCR es neuronal y local; las decisiones no dependen de un LLM. Se mantiene el ERP, no se reemplaza por su CSV interno. El formato web se elige por el trabajo de revisar fuente y resultado juntos.

## 4:00–8:00 · Traza, cambio, escala y coste

En una copia de demo, registrar una respuesta y enseñar autor, referencia y resultado original del motor.
Actualizar un dato del maestro/ERP en un entorno sintético, preparar el cambio y mostrar antes/después, afectados, decisiones conservadas y OCR reutilizado.
La respuesta humana queda ligada a la evidencia: si cambia, se vuelve a consultar.
En Actividad y coste, separar medición de estimación. Usar benchmark-v02.json: ERP real, latencia normal, caché fría, hardware y límites.
Introducir tarifas reales en la calculadora; explicar que los minutos son declarados y no se conoce accuracy sin etiquetas.

## 8:00–10:00 · Recuperación y límites

Demostrar un fallo en la demo sintética, no destruir la ejecución de entrega:
`process --fault-after 0` corta entre extracción y commit. La prueba automatizada verifica recuperación tras caducidad del lease y unicidad.
También hay tests HTTP para 401, 429, 500, timeout y respuesta incompleta. Mostrar historia/error y trabajo pendiente.
No fingir un fallo LLM: no existe ese proveedor en el camino de ejecución. La alternativa elegida reduce esa dependencia.

## Antes de salir

Mantener resultados preparados, copia de seguridad y demo sintética separada. No editar los datos originales para fabricar un «antes/después». Llevar el plan actualizado y confirmar horario. No presentar el lote sintético de 40 documentos como lote oficial ni prometer 100 % de precisión.

Ensayo de recuperación/cambios:
```bash
python -m pytest tests/test_workspace.py tests/test_service.py tests/test_erp_web.py -q
```
