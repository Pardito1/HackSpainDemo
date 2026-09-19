# FactU · La mesa de las cuentas claras · v0.3

Para subir el proyecto a GitHub, lee [GITHUB.md](GITHUB.md). El ZIP contiene la solución completa, pruebas, documentación y una demo reproducible; no contiene la base de datos local ni los materiales oficiales. El repositorio de entrega del concurso es distinto.

Corrección 0.3: OCR sin mezclar número y fecha, etiquetas de procedencia, errores de entrada comprensibles, integridad de archivos/decisiones además de eventos y consulta obligatoria ante instrucciones sospechosas detectadas. 112 pruebas Python + 4 JavaScript pasan. La herramienta sigue siendo local, sin autenticación ni pagos reales; lote 2 y validación privada pendientes.

Método `modelo` (nuevo): tercer paso de lectura para páginas escaneadas cuyos campos el OCR local no resuelve. Un modelo multimodal **solo lee** valores con su evidencia literal; nunca decide, y cada lectura pasa una validación propia antes de aceptarse (ver «Lectura con modelo»). Cualquier fallo del proveedor deja el aviso `MODELO_NO_DISPONIBLE` y la factura en ESCALAR. 151 pruebas Python + 4 JavaScript pasan.

Para actualizar datos de una versión anterior, conserva una copia de la carpeta `data` con la app parada. Después ejecuta `factu --data data verify-audit`, `factu --data data reextract ID_DEL_LOTE` y `factu --data data process ID_DEL_LOTE`. Se conserva el historial; las respuestas cuyo contexto cambie requieren nueva revisión. No ignores una comprobación de integridad fallida ni borres el historial para hacerla pasar. Para pruebas del navegador: `node --test tests/test_frontend.mjs`.

Aplicación local y CLI para **conciliar facturas con pruebas**, consultar el ERP y proponer `PAGAR`, `NO_PAGAR` o `ESCALAR`. Hecha para el track Maisa «500 sombras de Alberto».

**Código funcional, no un sistema bancario de producción. No ejecuta pagos ni modifica el ERP.** Se ha probado sobre los 500 PDFs del primer lote, con OCR local y el bridge HTTP oficial. Los resultados no están contrastados con la referencia privada del jurado. La norma v4 y el segundo lote requieren validación cuando se publiquen.

## Qué incluye

- Bandeja web con filtros, carga de lotes y estados operativos.
- Lectura en embudo: texto nativo con PyMuPDF → OCR local RapidOCR/ONNX en páginas escaneadas → modelo multimodal solo para los campos que el OCR deja sin resolver (lee, nunca decide).
- Evidencia por campo: texto original, valor normalizado, página, coordenadas, método, transformaciones y candidatos contradictorios.
- Maestro Excel con referencias a celdas; hojas antiguas y fórmulas fuera de la fuente aprobada no deciden.
- ERP por HTTP/XML: autenticación, paginación completa, renovación de sesión y reintentos acotados. Se conservan las respuestas XML, sin guardar el token.
- Reglas deterministas, importes `Decimal`, identidad y política versionadas. El PDF nunca puede ordenar al sistema cambiar las reglas.
- Corrección humana con autor, motivo, previsualización y comprobación de que la evidencia no ha cambiado. No borra el dato original.
- Respuesta de Alberto separada de la corrección de lectura: autor, motivo, evidencia, tiempo dedicado y doble confirmación. La respuesta caduca si cambia su fundamento; vuelve a consulta.
- Cambios de Excel, ERP o política con vista previa de impacto, confirmación y reevaluación selectiva sin repetir OCR. Historial y decisiones no afectadas conservados.
- Mejora adicional implementada: borradores de consulta por proveedor con preguntas y facturas afectadas. Se descargan para revisar, nunca se envían ni autorizan pagos.
- SQLite con estados persistentes, leases recuperables, caché y control de duplicados entre lotes. Auditoría encadenada por hashes.
- Tiempos por expediente y por lote, costes externos, benchmark reproducible, pruebas automatizadas y validador de entrega.

## Arranque

Python 3.11+; probado con **Python 3.12 en macOS arm64**. macOS/Linux; para Windows utiliza WSL2 porque el bloqueo de procesos usa `fcntl`. Las otras plataformas no se han probado aquí.

Desde esta carpeta:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest -q
```

Instalación alternativa, resolviendo dependencias de tu plataforma:

```bash
python -m pip install -e '.[ocr,test]'
```

La descarga inicial de paquetes/modelos necesita Internet; los documentos se procesan localmente. Sin claves de LLM la app funciona igualmente: el método `modelo` es opcional y, si faltan credenciales, los escaneados sin resolver quedan en ESCALAR con aviso (ver «Lectura con modelo»). En Linux, OpenCV puede requerir las bibliotecas de sistema `libGL`/`libglib`. No se instala nada automáticamente fuera del entorno virtual.

### Con el repositorio oficial

Descarga los materiales desde el [repositorio oficial](https://github.com/ikurotime/500-sombras-de-alberto) o el canal del track y verifica sus hashes. Este paquete **no redistribuye los datos ni el código del ERP**.

En una terminal, desde la carpeta de los materiales, deja el ERP funcionando:

```bash
python3 alberto_erp.py
```

El ERP suministrado utiliza Python 3. Consulta su `MANUAL_ERP_2009.md`. Usa el modo normal para medir rendimiento; `--rapido` es únicamente para pruebas y debe declararse si se usa.

En otra terminal, desde este proyecto, activa `.venv` e importa el lote. Ajusta las rutas al lugar donde guardaste el repositorio:

```bash
factu --data data ingest \
  --pdfs ../500-sombras-de-alberto/facturas \
  --excel ../500-sombras-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx \
  --name 'Lote 1' --as-of 2026-09-19
```

El comando devuelve `batch_id`. Sustituye `ID_DEL_LOTE` en los siguientes comandos:

```bash
factu --data data sync-erp ID_DEL_LOTE
factu --data data process ID_DEL_LOTE
factu --data data serve --port 8080
```

Abre **http://127.0.0.1:8080**. También puedes importar PDFs y Excel desde la interfaz. Selecciona el lote y pulsa primero «Sincronizar ERP» y después «Procesar». La fecha `--as-of` es un contexto explícito de evaluación, no se toma del nombre del archivo.

Variables opcionales: `FACTU_DATA`, `ERP_URL`, `ERP_USER`, `ERP_PASSWORD`. Por defecto usa el usuario y clave sintéticos documentados por el reto (`alberto` / `FACTURAS2009`), en `http://127.0.0.1:8009`. No reutilices esas claves en sistemas reales. No incluyas credenciales en URLs ni en Git.

### Demo independiente de tres casos

Para probar el producto sin los materiales oficiales:

```bash
python scripts/make_demo.py --output demo-input
python scripts/demo_erp.py
```

Deja esa terminal abierta. En otra, con el entorno activado:

```bash
export ERP_URL=http://127.0.0.1:8019
factu --data demo-state ingest --pdfs demo-input/facturas --excel demo-input/maestro.xlsx --name 'Demo sintética' --as-of 2026-09-19
factu --data demo-state sync-erp ID_DEL_LOTE
factu --data demo-state process ID_DEL_LOTE
factu --data demo-state serve
```

Resultado esperado de los datos generados: `demo-1.pdf → PAGAR`, `demo-2.pdf → ESCALAR` (IBAN distinto), `demo-3.pdf → NO_PAGAR` (ERP ya pagada). La demo sintética no sustituye la prueba del ERP oficial.

## Cómo decide

| Salida | Política implementada del equipo |
|---|---|
| PAGAR | Todos los controles tienen evidencia suficiente y pasan. Es una propuesta, nunca una transferencia. |
| NO_PAGAR | Pedido inequívoco ya pagado, con identidad coherente; o copia byte a byte de otra factura del mismo pedido. |
| ESCALAR | Discrepancia, ambigüedad, dato ausente o lectura de calidad insuficiente. Se muestran las preguntas pendientes. |

Un fallo técnico que impide terminar el trabajo **no se disfraza de ESCALAR**: queda pendiente y bloquea la exportación. Una lectura completada pero incompleta sí puede requerir revisión humana. No se «rellena» un IBAN/NIF que falta usando el maestro para hacer que coincida.

La norma v3 está implementada en `factu/policy.py` y configurada en `factu/policies/v3.json`. Los criterios de `NO_PAGAR` son decisiones explícitas del equipo, no reglas supuestamente publicadas por Maisa. El checksum del IBAN se conserva como diagnóstico, pero no bloquea: los IBAN sintéticos del maestro fallan ese checksum. La regla del reto es la igualdad con el maestro.

## Lectura con modelo (tercer método)

El embudo de lectura es texto nativo → OCR local → modelo, y cada paso solo actúa donde el anterior no llega. El modelo multimodal se consulta únicamente si una página necesitó OCR **y** algún campo distinto del número de factura sigue sin lectura firme. Devuelve, por campo, el valor, la **línea literal del documento de la que lo copió** y la página; entra como un candidato más (`method="modelo"`) junto a los del OCR: sin lectura previa firme resuelve el campo, y si contradice una lectura OK del OCR el campo queda en CONFLICT y la factura se consulta. El modelo **nunca decide**: `PAGAR`/`NO_PAGAR`/`ESCALAR` sale siempre del motor de reglas.

Toda lectura del modelo pasa una validación previa, porque un modelo puede calcular o inventar en lugar de copiar:

- NIF del emisor: forma de NIF/CIF de 9 caracteres; el CIF del cliente nunca se acepta como emisor.
- IBAN: `ES` + 22 dígitos (formato).
- Pedido: formato `PO-AAAA-NNNN` tal cual impreso; no se reconstruyen guiones perdidos.
- Importes y tipo de IVA: el valor debe aparecer en la evidencia literal; un importe derivado se rechaza como `inferido`.

La validación es formato + evidencia literal + contraste con maestro y ERP: el dígito de control del NIF y el módulo 97 del IBAN se registran en el candidato como diagnóstico (`checksum`), sin bloquear, porque los identificadores del caso son sintéticos (en el maestro solo 1 de 12 NIF pasa el dígito de control y 0 de 12 IBAN pasan el módulo 97). Un valor mal leído no coincide con el maestro y la política lo escala. Lo rechazado por formato queda como INVALID con su motivo, visible en el expediente, y la política escala. Un rechazo nunca se apoya solo en el modelo: si el número de pedido lo leyó únicamente el modelo y el ERP da ese pedido por pagado, la factura se consulta (ESCALAR), no se marca NO_PAGAR.

Configuración por variables de entorno (en `.env`, fuera de Git): `LLM_BACKEND` (`cf_workers_ai` por defecto, `cf_anthropic` opcional vía AI Gateway), `CF_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CF_GATEWAY_ID`, `CF_AIG_TOKEN` o `LLM_ANTHROPIC_URL` para el backend Anthropic, `MODELO_EXTRACCION` y `LLM_TIMEOUT_S`. Los precios (`LLM_PRECIO_NEURONA_MIL`, `LLM_PRECIO_IN_MTOK`, `LLM_PRECIO_OUT_MTOK`) también son variables, nunca constantes en el código.

Failover medido, no prometido: sin credenciales no se toca la red y cada escaneado sin resolver queda en ESCALAR con el aviso `MODELO_NO_DISPONIBLE: sin_clave` (lote 1 completo en 48,0 s en un MacBook Air M1, ERP con latencia real, reparto 433/9/58). Con un token inválido el proveedor responde 401 y las 26 páginas afectadas dejan el aviso `auth` con el mismo reparto prudente (85,7 s). Timeouts, 429 y 5xx tienen reintentos acotados y un cortacircuito por proceso: tras 3 errores de red seguidos, el resto del lote no llama al proveedor y sale en segundos con el aviso `circuito_abierto`; `process` lo rearma al arrancar. Cualquier fallo final es un aviso en la extracción, nunca una excepción ni un resultado inventado. La caché de extracción incluye backend, modelo y disponibilidad de credenciales: al recuperarlas, `reextract` + `process` reextrae el lote (los PDF con texto tardan segundos y no llaman al modelo) y solo los escaneados pendientes consultan el modelo.

Coste: cada llamada queda registrada por documento en `costs` (etapa `modelo`) con tokens, neuronas de Workers AI y `external_eur` calculado con el precio configurado. Medido sobre el lote 1 completo desde la app (MacBook Air M1, ERP con latencia real, Workers AI `@cf/meta/llama-4-scout-17b-16e-instruct`, `response_format` json_schema aceptado por el endpoint): 25 páginas leídas por el modelo, 2.856 tokens de entrada y ≈ 300 de salida por página, 93,3 neuronas por página (2.332 en total), ≈ 0,026 $ el lote entero a 0,011 $/1.000 neuronas — dentro de la cuota gratuita de 10.000 neuronas/día. Latencia: 10,2 s por página de media (5,9–24,9 s), 255 s de modelo dentro de los 5 min 20 s del `process` completo. Reparto con modelo: 438 PAGAR / 9 NO_PAGAR / 53 ESCALAR (con OCR solo: 433/9/58); 6 de los 29 escaneados quedan en PAGAR y los 23 en ESCALAR llevan motivo campo a campo (lecturas OCR/modelo en conflicto, formatos rechazados o identidad/IBAN que no casan con el maestro).

## Revisión humana

Abre una factura y pulsa una evidencia para verla sobre el PDF. En «Resolver una lectura» indica campo, valor comprobado, revisor y justificación. **Simula primero** y confirma después: el motor vuelve a ejecutar todos los controles.

Solo corrige errores de lectura con evidencia. No pongas el IBAN del maestro si el PDF muestra otro. En «Registrar una respuesta» Alberto puede mantener la consulta, justificar NO_PAGAR o respaldar PAGAR. Este último exige todos los controles técnicos: solo permite resolver expresamente un conflicto de precedencia Excel/ERP o una regla adicional de negocio, con referencia de evidencia. No admite saltarse cuentas, importes, identidad, duplicados ni pagos previos. El resultado del motor y la respuesta humana se conservan por separado. Si cambia su fundamento, la respuesta anterior deja de aplicarse y el caso vuelve a ESCALAR.

En «En común» se agrupan preguntas por proveedor y se descarga un borrador de consulta. La agrupación no significa que una sola validación autorice todos los pagos. La corrección compartida de lecturas exige misma causa/evidencia/versiones y selección explícita. Autor escrito no equivale a identidad autenticada: esta versión es local, de operador único.

## Cuando cambia una fuente

En «Fuentes y cambios», selecciona el lote, prepara un Excel/política nueva o consulta una nueva versión del ERP. Indica quién introduce el cambio y por qué. La vista previa muestra decisiones afectadas, resultado antes/después y trabajo reutilizado. Solo al confirmar cambia la fuente vigente; se conserva el historial. Un cambio de norma requiere revisar expresamente su correspondencia con la política implementada. No se convierte texto libre en reglas automáticamente.

Los cambios del ERP se comparan por pedido; los del maestro por proveedor/pedido/norma. Una dependencia desconocida invalida conservadoramente. Una nueva política o versión de código puede afectar a todo el lote. Cero repeticiones de OCR en estos cambios. Si se interrumpe tras aplicar la fuente, las decisiones afectadas quedan pendientes y se recuperan con «Reevaluar».

Una previsualización ERP fallida conserva la fuente vigente y registra el error: no se ha aplicado el cambio. «Sincronizar ERP completo», en cambio, refresca el lote completo e invalida resultados si falla. La interfaz distingue ambas operaciones.

## Segundo lote y cambios de norma

1. Conserva los originales y los resultados/versiones del primer lote.
2. Lee la norma v4 y registra qué cambia; no se interpreta automáticamente con un LLM.
3. Configura una nueva política JSON. El motor admite cambios de tolerancia, monedas y reglas adicionales `eq`, `ne`, `lte`, `gte` sobre campos extraídos. Semánticas nuevas requieren código y pruebas; no se ignoran campos desconocidos.
4. Arranca el ERP oficial con la actualización del lote 2 según su manual (su opción `--lote2` fusiona los asientos).
5. Importa el nuevo directorio con `--policy ruta/politica-v4.json`, sincroniza ese lote y procésalo. No existe un límite de 500/40 codificado.
6. Se conservan snapshot/política propios por lote y se revisan duplicados entre lotes. Mientras haya documentos sin terminar, no se finalizan decisiones dependientes del índice global de duplicados.

El adaptador Excel espera `Proveedores`, `Pedidos_2026`, `Norma_Pagos_v3` y las columnas del libro inicial. Si cambia ese esquema, adapta `master.py` con tests antes de importar. Versionar una política no es afirmar compatibilidad automática con una norma desconocida.

```bash
factu --data data policy ID_DEL_LOTE --file politica-v4.json --actor 'Equipo'
factu --data data evaluate ID_DEL_LOTE
```

Reevaluar una política reutiliza la extracción. Si cambia el extractor, incrementa `VERSION`, reinicia el servidor y solicita una nueva extracción:

```bash
factu --data data reextract ID_DEL_LOTE
factu --data data process ID_DEL_LOTE
```

La caché incluye hash del PDF, versión de extractor, bibliotecas, modelos OCR y modo de lectura. Las decisiones incluyen hash del código, política y fuentes.

## Fallos y recuperación

```bash
factu --data data retry ID_DEL_LOTE
factu --data data process ID_DEL_LOTE
factu --data data verify-audit
```

Los errores de extracción tienen reintentos acotados y espera creciente. Una ejecución no duerme esperando trabajos futuros: vuelve a ejecutar `process`/«Recuperar» tras la espera. Si se mata el proceso, una reserva viva no se roba: caduca a los 10 minutos y el siguiente worker recupera el trabajo. No se borra la base de datos para reanudar.

El modo `process --fault-after 0` interrumpe deliberadamente después de extraer y antes de guardar. Úsalo **en una demo nueva**, no sobre el estado de entrega. Los tests simulan la caducidad del lease sin tener que esperar 10 minutos.

Una sincronización ERP fallida invalida la decisión actual de su lote, conserva su historia y bloquea la exportación hasta obtener un snapshot completo. No se consulta directamente el CSV interno del ERP para eludir sus fallos.

## Mediciones y costes

```bash
factu --data data metrics ID_DEL_LOTE
python scripts/benchmark.py --pdfs ../500-sombras-de-alberto/facturas \
  --excel ../500-sombras-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx \
  --data benchmark-nuevo --as-of 2026-09-19 --erp-mode normal \
  --report benchmark.json
```

El benchmark exige un directorio nuevo y mide importación, ERP HTTP con reintentos, extracción/OCR y decisiones. Incluye hardware, memoria máxima del proceso, p50/p95 de extracción y tiempo extremo a extremo. Consulta `docs/benchmark-lote1.json` para una ejecución medida, si está incluido.

Coste externo de inferencia: 0 € con el método `modelo` apagado; activado, cada llamada queda en `costs` con neuronas/tokens y su `external_eur` según el precio configurado. **No significa coste total cero**. Completa las tarifas reales de infraestructura y tiempo humano para usar:

`coste_por_factura = (coste_proveedores + horas_infraestructura × €/h + minutos_revisión × €/min) / facturas_procesadas`

Los tiempos de la pantalla son acumulados, incluidos reintentos/reprocesamientos; no deben venderse como una ejecución fría. La precisión requiere etiquetas independientes. No confundas porcentaje automatizado con accuracy ni score OCR con probabilidad calibrada.

## Entrega del hackathon

Este es el **repositorio de la solución**, no el repositorio público de resultados. El de entrega debe estar separado y contener exactamente:

```text
outcomes.jsonl
outcomes_lote2.jsonl
albertitos_plan.pdf
```

```bash
factu --data data export ID_LOTE1 --output ../entrega/outcomes.jsonl
factu --data data export ID_LOTE2 --output ../entrega/outcomes_lote2.jsonl
python scripts/validate_submission.py ../entrega --lote1 ../datos/facturas --lote2 ../datos/lote2
```

El plan actualizado de esta versión está en `docs/albertitos_plan.pdf`, con arquitectura y cinco ADRs; revisadlo al incorporar el lote 2. Sustituye como referencia al borrador de propuesta anterior del chat. No generamos un segundo JSONL vacío para fingir que hemos procesado datos que todavía no tenemos. La auditoría de materiales está en `docs/MATERIALS.md` y el estado de cumplimiento en `docs/COMPLIANCE.md`.

El validador comprueba nombres exactos, unicidad, cobertura, valores permitidos y PDF abrible; **no tiene acceso a la referencia privada y no acredita APTO**. La documentación compartida presenta 10:30 y 11:00 como horas distintas: confirmar con la organización y entregar antes de la más temprana hasta aclararlo. Nada se publica ni se envía automáticamente.

## Límites que conviene defender con honestidad

- Un worker y una máquina. El bloqueo serializa cambios para evitar carreras; no es un sistema distribuido.
- OCR genérico, no perfecto. Escaneos borrosos, faxes, rotaciones o caracteres confusos pueden requerir revisión humana.
- Extractor orientado a campos de factura ES/EN y pedidos `PO-año-número`. No hay extracción general de tablas/líneas, abonos complejos, varios tipos de IVA ni adaptación universal de formatos.
- El LLM solo lee campos y siempre con evidencia literal validada; no hay orquestador multiagente. Si el proveedor cae, rate-limita o devuelve basura, la lectura degrada a OCR + consulta humana con aviso; el failover se demuestra retirando las credenciales.
- No hay SSO, roles, cifrado de base de datos, almacenamiento WORM ni separación de tenants. No exponer a Internet ni usar datos reales sin endurecimiento.
- El historial encadenado detecta modificaciones ordinarias; un administrador con acceso total puede reescribir base y cadena. Guardar el hash final fuera de la máquina reforzaría la evidencia.
- «PAGAR» es coherencia con las fuentes registradas; no acredita autenticidad legal del PDF, cuenta bancaria o persona revisora.

## Estructura

`factu/extract.py`: extracción; `modelo.py`: lectura con modelo multimodal y validación de sus lecturas; `master.py`: Excel; `erp.py`: integración; `policy.py`: reglas; `db.py`: estado/evidencias; `service.py`: flujo; `web.py`: interfaz/API; `cli.py`: terminal; `tests/`: pruebas; `scripts/`: demo, benchmark y validador; `docs/`: decisiones técnicas.

Las dependencias conservan sus licencias. En particular, revisa la licencia AGPL/comercial de PyMuPDF antes de redistribuir o desplegar un servicio propietario; este paquete no concede licencias sobre dependencias ni datos de terceros.
