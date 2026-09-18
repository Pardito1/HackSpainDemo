# MAISA TRACK · 500 sombras de Alberto

**Construid una solución en el formato que el problema merezca. Defended por qué.**

Alberto procesa facturas, Excel y datos de un ERP legado. Hoy son 500 facturas; mañana querrá nuevos tipos de archivo, más volumen y respuestas aunque un proveedor de modelos falle. Vuestro trabajo no es acertar un benchmark: es construir un sistema al que Alberto pueda confiar una operación real.

| Cuándo | Dónde | Equipos | Caso común |
| --- | --- | --- | --- |
| 18-20 sep 2026 | ETSIT UPM, Madrid | 2-5 personas, hasta 15 equipos | 500 Sombras de Alberto |

## El reto

Recibís 500 Sombras de Alberto: 500 facturas en PDF, un Excel caótico y un ERP de 2009. Construid una solución que procese ese mundo y tome decisiones de pago. El formato es libre: un binario de backend, una herramienta para agentes, una CLI, una app web o algo distinto. Elegidlo porque resuelve mejor el problema, no porque sea lo habitual.

La Caja es el caso común para comprobar que el sistema funciona. La organización conserva los resultados esperados y los usa solo para validar entregas. La competición empieza después: queremos ver vuestro criterio de producto e ingeniería.

## Lo que queremos entender

En la defensa tendréis que sostener estas seis cuestiones:

1. **Producto, arquitectura y ADRs.** ¿Qué problema resolvéis, para quién, y por qué esta forma de producto, arquitectura y uso de agentes era la elección correcta? Compartid el resumen de las decisiones y alternativas que registrasteis.
2. **Trazabilidad y observabilidad.** ¿Cómo seguís una decisión desde el input hasta el resultado? ¿Qué señales permiten a Alberto detectar errores, reintentos, trabajo pendiente y coste?
3. **Escala, evolución y coste.** ¿Cuántos archivos procesáis por segundo, con qué hardware y bajo qué condiciones? ¿Cómo calculáis el coste? Si Alberto incorpora PDFs escaneados, emails, hojas de cálculo u otros tipos de archivo, ¿qué cambia: configuración, conectores, prompts, esquemas o código?
4. **Resiliencia y recuperación.** ¿Qué ocurre si vuestro proveedor de LLM falla, rate-limita o devuelve una respuesta inválida? ¿Cómo conserváis el trabajo, evitáis duplicados, degradáis y recuperáis?
5. **Calidad de ejecución.** ¿Es una solución clara, proporcionada y agradable de operar? ¿Sus decisiones y límites tienen sentido para Alberto?
6. **Bonus: una mejora para Alberto (+10!).** ¿Qué necesidad adicional habéis detectado, implementado y mostrado, más allá del flujo obligatorio?

No hay una respuesta o interfaz única. Un backend pequeño y bien razonado puede superar a una aplicación grande sin criterio.

## La Caja y la validación

Para participar por el premio, vuestro sistema debe procesar la Caja y entregar sus outcomes en JSONL. La organización los contrasta contra los resultados de referencia, que no se publican.

La validación es **binaria y no da puntos**: debe haber exactamente un outcome por cada archivo y su `result` debe coincidir con uno de los resultados esperados de la referencia privada. Si no superáis la validación, podéis defender el proyecto y recibir feedback, pero no optar al premio. No se publica un ranking y esos resultados no rompen empates.

El sábado Alberto enviará un lote adicional y una regla nueva. El domingo podrá cambiar un dato de la Caja. La organización conoce el efecto esperado para comprobar que la demo es real; no se asignan puntos por el número de coincidencias. La conversación se centra en cómo diseñasteis el cambio, el reprocesado y los límites de vuestro sistema.

## Qué recibís

| Viernes 21:00 | Sábado 18:00 |
| --- | --- |
| 500 facturas PDF, Excel, ERP local| 40 facturas adicionales, actualización del ERP y norma v4 |
| Esta guía y la rúbrica | Escenario sorpresa |

## Qué se entrega (domingo 10:30, Madrid)

Compartid el `teamId` y la URL de un repositorio público de GitHub. Usad un repositorio separado para esta entrega: no subáis vuestra solución, credenciales ni una aplicación ejecutable. La única documentación requerida es `albertitos_plan.pdf`.

La raíz del repositorio debe contener exactamente estos tres archivos:

```text
la-caja-outcomes/
├── outcomes.jsonl
├── outcomes_lote2.jsonl
└── albertitos_plan.pdf
```

Cada archivo contiene un objeto JSON por archivo de La Caja. Solo son obligatorios `file_id` y `result`. Podéis añadir campos de traza si os ayudan a explicar la decisión durante el pitch.

```json
{"file_id":"factura_5518.pdf","result":"PAGAR"}
{"file_id":"FA-4475_informática.pdf","result":"ESCALAR"}
```

`albertitos_plan.pdf` debe tener dos secciones: **Arquitectura** y **ADRs / trade-offs**. La primera debe explicar componentes, flujo de datos y estado, reparto entre agentes, modelos y personas, y cómo se observan y recuperan los fallos. La segunda debe resumir entre dos y cinco decisiones relevantes, con contexto, alternativas consideradas, decisión, consecuencias aceptadas y evidencia. No hace falta que sea largo: debe servir para preparar la defensa y hacer explícito vuestro criterio.

La organización clonará el repositorio a las 10:30, registrará el commit y ejecutará su verificador privado sobre los dos JSONL. No ejecutará código del equipo y no verá ni pedirá credenciales. La ausencia o mala calidad de `albertitos_plan.pdf` no elimina la elegibilidad si los dos JSONL son correctos, pero puede dejar sin puntos el criterio de Producto, arquitectura y ADRs. Los organizadores podrán hacer preguntas sobre cualquier decisión, alternativa o trade-off registrado en el PDF.

## Cómo se evalúa

Un solo tribunal ve todos los proyectos con el mismo guion de 10 minutos. La validación funcional ya estará resuelta y no ocupa la puntuación.

1. **Demo y contexto (2 min).** Enseñad la solución y el problema concreto que resuelve.
2. **Arquitectura y ADRs (2 min).** Explicad el formato, la arquitectura, el reparto entre agentes, modelos y personas, y el resumen de decisiones registradas.
3. **Trazabilidad, observabilidad, escala y coste (4 min).** Seguid una decisión real, mostrad las señales operativas y defended capacidad, fórmula de coste, supuestos y evolución ante nuevos inputs. Si habéis construido una mejora adicional para Alberto, enseñadla durante la demo.
4. **Resiliencia y preguntas (2 min).** Explicad o demostrad qué sucede ante una caída del proveedor de LLM, y responded a preguntas del tribunal.

| Criterio | Qué mide | Puntos |
| --- | --- | ---: |
| **Producto, arquitectura y ADRs** | Problema, formato, decisiones, alternativas y trade-offs | 35 |
| **Trazabilidad y observabilidad** | Decisiones auditables, estado y señales operativas | 20 |
| **Escalabilidad y coste** | Capacidad, límites, cálculo económico y evolución | 25 |
| **Resiliencia y recuperación** | Fallos de proveedor, estado, degradación y recuperación | 10 |
| **Calidad de ejecución** | Claridad, proporción, experiencia y calidad de ejecución | 10 |
| **Bonus: mejora adicional para Alberto** | Necesidad real, originalidad, implementación y demostración | 10 |

## Qué no os pedimos

- No una interfaz concreta ni un stack concreto.
- No un benchmark de OCR ni una demo de un modelo aislado.
- No una promesa abstracta de escala: explicad las condiciones y evidencias de vuestras cifras.
- No alta disponibilidad perfecta en un fin de semana: sí una estrategia honesta cuando un proveedor falla.

Todos los datos son sintéticos.

## Premio

Un viaje al HQ de Maisa en Valencia para vivir la experiencia Maisa, más un teclado para cada integrante del equipo ganador.
