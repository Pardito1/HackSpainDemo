# Defensa de 5 minutos + 5 de preguntas · v0.10.0

Frase de apertura: **«FactU no decide por intuición: cada pago conserva la
prueba, y cuando una fuente cambia sabemos exactamente qué vuelve a revisar
Alberto.»**

## 0:00–0:30 · El problema, en vocabulario Maisa

Alberto tiene 540 facturas y un ERP legado. El trabajo no es «leer PDFs»: es
un **proceso** con **excepciones** que se resuelven a mano y una obligación de
**cumplimiento**: por qué se paga o no se paga cada factura debe quedar
trazable. FactU convierte ese proceso en propuestas revisables, con la
excepción como salida legítima y la traza como evidencia auditable.

## 0:30–1:15 · Camino feliz, corto

Abrir la bandeja del Lote 2 ya procesado: **40 documentos, 24 `PAGAR`, 1
`NO_PAGAR`, 15 `ESCALAR`**, con auditoría íntegra. Elegir un `PAGAR` con
maestro, ERP y aritmética en verde y abrir la evidencia por campo: página,
caja, método y valor normalizado. Recordar que el reparto es aplicación de la
política v3 a un snapshot; no es métrica de precisión ni un pago real.

## 1:15–2:30 · El caso difícil

Tres expedientes concretos, sin adornos:

- Factura en **JPY** sin conversión trazable: FactU conserva `JPY` si está
  impreso, no lo transforma a EUR por idioma, NIF, IBAN o dirección; la
  política v3 escala hasta que exista FX autorizada.
- Factura con **importe tachado o corregido a mano**: el detector de riesgo
  bloquea `PAGAR` aunque el resto parezca legible.
- Historial ERP de `PO-2026-0071`: hay dos asientos (`PENDIENTE` y una
  actualización posterior `PAGADA`). FactU conserva ambos, selecciona el más
  reciente porque pedido, proveedor, NIF e importe coinciden y la fecha máxima
  es única, y propone `NO_PAGAR`. Un empate o cualquier contradicción escala.

## 2:30–3:30 · La traza y el cambio de fuente

Abrir el expediente completo del `PAGAR` anterior y recorrer la evidencia por
campo (valor leído, valor normalizado, página, caja, método, versión de
reglas, versión de fuentes). Después, en una copia de estado, preparar una
actualización del Excel o de la política y enseñar la **previsualización de
impacto antes de aplicar**: qué facturas cambian, cuáles se conservan, cuáles
reutilizan OCR sin volver a leer. No se toca la ejecución que se vaya a
entregar.

Ensayo verificado (20/09, copia `estado-revision`, ERP oficial con lote 2): en
«Datos y actualizaciones» → «Comparar una actualización» → «Datos contables
(ERP)» → «Consultar ERP y ver facturas afectadas», el preview responde **«39
mantienen su resultado / 0 pasan a revisión / 1 cambia a otro resultado»** y
«Revisar cambios» señala `2026-08-22_P010.pdf`: Requiere revisión → No pagar,
porque el pedido compartido `PO-2026-0071` ya consta pagado. Es la frase clave
del bloque: *el sistema te dice qué va a cambiar antes de que cambie nada*.

## 3:30–4:30 · Límites honestos y coste medido

- Sin llamadas al proveedor `modelo` operativo: el coste externo de inferencia
  es **0 €** en las cifras vigentes. RapidOCR y las reglas corren en local.
- End-to-end del Lote 1 (500 facturas) en **53,8 s** sobre MacBook Air M1,
  ERP con latencia real, sin modelo externo.
- `ESCALAR` no es un cajón de sastre: se reserva para evidencia
  ausente/contradictoria, moneda sin conversión, historia ERP ambigua, IBAN
  fuera de maestro, duplicado no exacto o anotación manual. Un fallo técnico
  sigue siendo técnico, nunca se disfraza de `ESCALAR`.
- No hay orquestador multiagente, ni SSO, ni WORM: no exponer a Internet ni
  usar datos reales sin endurecimiento. El link público del pitch se asume en
  voz alta como demo desechable (copia del estado, datos ya públicos del reto).

## 4:30–5:00 · Cierre

**«El OCR aumenta cobertura; el código limita qué puede automatizarse. Cuando
no hay prueba, FactU explica la duda y conserva el contexto para resolverla.»**

## Si la demo muestra ambos lotes juntos

Contarlo antes de que pregunten: el estado conjunto de los dos lotes da **458
propuestas de pago / 9 no pagar / 73 en revisión** (verificado el 20/09 en la
base de `estado-entrega`), no 435+24 y 9+1 y 56+15, porque `factura_4635.pdf`
(Lote 1) comparte el pedido `PO-2026-0071` con `2026-08-22_P010.pdf` (Lote 2)
y, cuando ambas conviven, la detección de duplicados **interlote** escala las
**dos caras del mismo pedido** para que Alberto decida cuál corresponde al
pago. Las entregas se generaron por separado y también son coherentes:
`outcomes.jsonl` (Lote 1, antes de existir el Lote 2) dice `PAGAR`, y
`outcomes_lote2.jsonl` dice `NO_PAGAR` porque el pedido ya constaba `PAGADA`
en el ERP — regla 5, nunca pagar dos veces. Es un punto a favor de la
arquitectura si se explica en el momento adecuado.

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
