# Defensa de 10 minutos · v0.10.0

Frase de apertura: **«FactU no decide por intuición: cada pago conserva la
prueba, y cuando una fuente cambia sabemos exactamente qué vuelve a revisar
Alberto.»**

## 0:00–2:00 · Resultado y bandeja

Abrir el Lote 2 ya procesado: **40 documentos, 19 `PAGAR`, 1 `NO_PAGAR`, 20
`ESCALAR`**, con auditoría íntegra. Aclarar inmediatamente que el reparto no
es una métrica de precisión ni un pago real: muestra la aplicación de la
política v3 a un snapshot y fuentes concretos.

Elegir un `ESCALAR` breve y visual, por ejemplo una factura sin moneda o una
en JPY con la dirección `Tokyo, España`. Enseñar que FactU conserva `JPY` si
está impreso y **no** lo transforma a EUR por el idioma, NIF, IBAN o dirección.
La pregunta es accionable: falta una conversión autorizada, no un porcentaje
opaco.

## 2:00–4:00 · Extracción que ayuda sin decidir

Mostrar el expediente y su recorrido: PDF original → lectura nativa → segundo
testigo RapidOCR cuando un defecto crítico lo justifica → campos con
página/caja/método → reglas.
El perfil `lote2_ocr_v1` solo se usa en los 40 nuevos; Lote 1 conserva su ruta
original. RapidOCR se activó en 3 de 42 páginas, no en todo el lote.

Decir la métrica con precisión: «contra transcripciones manuales internas
revisadas, el holdout interno agrupado de 10 documentos da 99,0 % de exact
match macro de campos y 8/10 expedientes con campos de riesgo autoaceptados y
correctos frente a etiqueta». Añadir de inmediato: «no es accuracy de pagos,
de RapidOCR aislado ni validación privada; el split actual solo separa
proveedores». Esto demuestra medición seria, no un número publicitario.

Abrir `e16`, `e17` o `e18` y remarcar el criterio: fecha manuscrita, factura
entera manuscrita o importe tachado/corregido se detecta como riesgo y bloquea
`PAGAR`, aunque otro campo parezca legible.

## 4:00–6:00 · Fuentes, cambios y ERP

Abrir el caso `PO-2026-0071`. El ERP tiene dos registros: `PENDIENTE` y una
actualización posterior `PAGADA`. FactU conserva ambos y solo selecciona el
último porque pedido, proveedor, NIF e importe coinciden y la fecha máxima es
única; por eso propone `NO_PAGAR`. Un empate o cualquier contradicción escala.

Después, en una copia de estado, preparar una actualización del Excel o de la
política y enseñar **antes de aplicar** el alcance: facturas afectadas,
decisiones que cambian y decisiones que se conservan. No modificar los
originales ni la ejecución que se vaya a entregar. Recalcular usa evidencias y
OCR existente; no vuelve a cobrar/leer sin necesidad.

## 6:00–8:00 · Seguridad y trabajo humano útil

Mostrar un documento con una instrucción impresa para el agente o un cambio de
IBAN no autorizado. El PDF es dato no fiable: no puede editar política,
proveedor, salida ni invocar ERP. El extractor devuelve campos cerrados; las
reglas versionadas y `Decimal` deciden.

Las revisiones no son un cajón de sastre. `ESCALAR` se reserva para evidencia
ausente/contradictoria, moneda sin conversión, historia ERP ambigua, IBAN fuera
de maestro, duplicado no exacto o anotación manual. En «Consultas a
proveedores», agrupar las dudas por proveedor crea un borrador descargable;
nunca envía correo ni aprueba facturas en bloque.

## 8:00–10:00 · Resiliencia y límite honesto

En la demo sintética (no sobre la entrega), ejecutar `process --fault-after 0`
para cortar entre extracción y commit. Enseñar estado persistente, lease y
reanudación sin duplicar. Mencionar reintentos 401/429/500/timeout del ERP y
que un fallo técnico sigue siendo técnico, no se disfraza de `ESCALAR`.

Cerrar: **«El OCR aumenta cobertura; el código limita qué puede automatizarse.
Cuando no hay prueba, FactU explica la duda y conserva el contexto para
resolverla.»**

## Guion histórico · v0.2

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
