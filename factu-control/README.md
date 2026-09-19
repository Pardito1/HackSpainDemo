# FactU v0.10.0

Aplicación local y CLI que, sobre facturas PDF cruzadas con un maestro Excel y un ERP legado, propone `PAGAR`, `NO_PAGAR` o `ESCALAR` con traza auditable por campo. El modelo y el OCR **leen**; el motor de reglas determinista **decide**. Hecha para el track Maisa «500 sombras de Alberto».

Contra transcripciones manuales internas revisadas del Lote 2 público, el holdout interno agrupado alcanza **99,0 % de exact match macro de campos** y 8/10 expedientes con campos de riesgo autoaceptados y correctos frente a etiqueta; no es una métrica de precisión de pagos ni de la referencia privada del jurado, no compara `PAGAR`/`NO_PAGAR`/`ESCALAR` con etiquetas contables ni es una garantía fuera de este lote.

La aplicación se ejecuta con `python -m factu`, dentro de `factu-control`. Conserva tu carpeta de estado: se admite tanto `factu.sqlite3` como una única base antigua `alberto.sqlite3`; si están ambas, se pide elegir sin borrar ninguna. Haz copia de seguridad con la app parada antes de actualizar.

## Cifras vigentes (medidas)

Ejecuciones locales de 2026-09-20 en **MacBook Air M1**, ERP oficial con **latencia real**, **sin modelo externo** operativo (embudo texto nativo → RapidOCR local; el proveedor `modelo` no interviene):

- **Lote 1 · 500 facturas:** 435 `PAGAR` / 9 `NO_PAGAR` / 56 `ESCALAR`, extremo a extremo en 53,8 s.
- **Lote 2 · 40 facturas:** 24 `PAGAR` / 1 `NO_PAGAR` / 15 `ESCALAR`, extremo a extremo en 8,3 s.
- **Pruebas:** 345 pruebas Python + 15 de Node en verde (28,3 s, mismo M1).
- **Coste externo de inferencia:** 0 €. Sin llamadas facturables al proveedor `modelo`; RapidOCR y las reglas son locales. No es coste total (no incluye hardware ni tiempo humano).

Estos repartos son la aplicación de la política v3 sobre las fuentes registradas en esa fecha y **no son métrica de precisión** frente a la referencia privada del jurado, que no publica su umbral. Cualquier nueva norma o lote requiere evaluación y versionado antes de ampliar automatizaciones. La documentación histórica se mantiene en [`docs/CHANGELOG.md`](docs/CHANGELOG.md); las notas completas de la release en [`docs/RELEASE-v0.10.0.md`](docs/RELEASE-v0.10.0.md).

El repositorio completo contiene los materiales oficiales ya aportados por el equipo. El ZIP creado por `scripts/package.py` contiene solo la app. Los resultados y el plan de la ejecución local 0.9.1 están separados en `../entrega-parcial-v0.9.1/`; no se han regenerado ni atribuido al motor integrado 0.10.0.

**Para las 500 facturas reales: [PROCESAR-500.md](PROCESAR-500.md).** Incluye comandos para Mac y Windows con WSL2; no uses el generador de demo para importar el lote oficial. Para subir el proyecto a GitHub, lee [GITHUB.md](GITHUB.md). El repositorio de entrega del concurso es distinto.

**Código funcional, no un sistema bancario de producción. No ejecuta pagos ni
modifica el ERP.** Se ha probado sobre los 500 PDFs iniciales y los 40 PDFs
públicos de Lote 2, con OCR local y el bridge HTTP oficial. Los resultados no
están contrastados con la referencia privada del jurado.

## Qué incluye

- Bandeja web con filtros, carga de lotes y estados operativos.
- Lectura en embudo: texto nativo con PyMuPDF → OCR local RapidOCR/ONNX en páginas escaneadas → modelo multimodal solo para los campos que el OCR deja sin resolver (lee, nunca decide). Lote 2 añade un segundo testigo RapidOCR multilingüe, aislado por perfil y con coordenadas/confianza.
- Evidencia por campo: texto original, valor normalizado, página, coordenadas, método, transformaciones y candidatos contradictorios.
- Maestro Excel con referencias a celdas e histórico parcial de pedidos como alerta revisable. Las otras hojas y las fórmulas no se ejecutan ni se toman como instrucciones.
- ERP por HTTP/XML: autenticación, paginación completa, renovación de sesión y reintentos acotados. Se conservan las respuestas XML, sin guardar el token.
- Reglas deterministas, importes `Decimal`, identidad y política versionadas. El PDF nunca puede ordenar al sistema cambiar las reglas.
- Corrección humana con autor, motivo, previsualización y comprobación de que la evidencia no ha cambiado. No borra el dato original.
- Respuesta humana separada de la corrección de lectura: autor, motivo, evidencia y doble confirmación. La ficha no solicita minutos; el tiempo declarado anteriormente se conserva en auditoría, sin inventar mediciones nuevas. La respuesta caduca si cambia su fundamento; vuelve a consulta.
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

La descarga inicial de paquetes/modelos necesita Internet. Texto y OCR se procesan localmente. Si configuras credenciales para el método `modelo`, las páginas escaneadas pendientes se envían al proveedor elegido; revisa sus condiciones antes de usar datos reales. Sin claves de LLM la app funciona igualmente y los escaneados sin resolver quedan en ESCALAR con aviso (ver «Lectura con modelo»). En Linux, OpenCV puede requerir `libGL`/`libglib`. No se instala nada automáticamente fuera del entorno virtual.

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

### Lote 2 oficial · 40 PDFs

El Lote 2 se ejecuta por una ruta separada: valida los 40 nombres y los CSV
incrementales, fusiona el ERP por HTTP y fija `lote2_ocr_v1` en el lote. No
mezcla ni reextrae el lote de 500. Arranca el bridge con su actualización:

```bash
cd ../500-sombras-de-alberto
python3 alberto_erp.py --lote2 erp_export_lote2.csv
```

En otra terminal, desde `factu-control`:

```bash
source .venv/bin/activate
factu --data data lote2 \
  --materials ../500-sombras-de-alberto \
  --as-of 2026-09-19 \
  --url http://127.0.0.1:8009
factu --data data serve --port 8080
```

El comando es idempotente: reanuda el mismo lote si el manifiesto y las
fuentes coinciden. Si el ERP no anuncia la actualización o falta uno de los
40 PDFs/CSV, se detiene antes de publicar resultados.

Variables opcionales: `FACTU_DATA`, `ERP_URL`, `ERP_USER`, `ERP_PASSWORD`. Por defecto usa el usuario y clave sintéticos documentados por el reto (`alberto` / `FACTURAS2009`), en `http://127.0.0.1:8009`. No reutilices esas claves en sistemas reales. No incluyas credenciales en URLs ni en Git.

### Demo independiente de cuatro casos

Para probar el producto sin los materiales oficiales:

```bash
python scripts/make_demo.py --output demo-input-v031
python scripts/demo_erp.py
```

Deja esa terminal abierta. En otra, con el entorno activado:

```bash
export ERP_URL=http://127.0.0.1:8019
python -m factu --data demo-state-v031 ingest --pdfs demo-input-v031/facturas --excel demo-input-v031/maestro.xlsx --name 'Demo sintética v0.3.1' --as-of 2026-09-19
python -m factu --data demo-state-v031 sync-erp ID_DEL_LOTE
python -m factu --data demo-state-v031 process ID_DEL_LOTE
python -m factu --data demo-state-v031 serve --port 8080
```

Resultado esperado: `demo-1.pdf → PAGAR`, `demo-2.pdf → ESCALAR` (IBAN distinto), `demo-3.pdf → NO_PAGAR` (ERP ya pagada), `demo-4.pdf → ESCALAR` (instrucción sospechosa, resto de controles correctos). Contadores: **4 facturas, 1 propuesta de pago, 1 no pagar, 2 consultas y 0 pendientes de procesar**. La demo sintética no sustituye la prueba del ERP oficial.

Si ejecutaste una versión anterior, detén y reinicia el ERP de demo con el script actualizado: debe anunciar «v0.3.1 · 4 pedidos». Genera los documentos e importa un estado nuevo como en estos comandos. Actualizar el código no cambia los PDFs que ya habías generado ni las decisiones guardadas. Conserva las carpetas anteriores.

La tabla refleja los filtros; los contadores superiores resumen el lote. «0 pendientes» significa procesamiento terminado. «0,00 €» es gasto externo registrado, no coste total: si activas un proveedor, configura sus tarifas y comprueba su consumo. El OCR local no hace llamadas de pago.

## Cómo decide

| Salida | Política implementada del equipo |
|---|---|
| PAGAR | Todos los controles tienen evidencia suficiente y pasan. Es una propuesta, nunca una transferencia. |
| NO_PAGAR | Pedido inequívoco ya pagado, con identidad coherente; o copia byte a byte de otra factura del mismo pedido. |
| ESCALAR | Discrepancia, ambigüedad, dato ausente o lectura de calidad insuficiente. Se muestran las preguntas pendientes. |

Un fallo técnico que impide terminar el trabajo **no se disfraza de ESCALAR**: queda pendiente y bloquea la exportación. Una lectura completada pero incompleta sí puede requerir revisión humana. No se «rellena» un IBAN/NIF que falta usando el maestro para hacer que coincida.

En Lote 2, una moneda no impresa o ambigua **no se convierte a EUR por el
idioma, NIF, IBAN o dirección**: se escala. Una factura en USD, JPY, GBP, CHF,
BRL o MXN se extrae y conserva con su ISO, pero la política v3 no puede
compararla con un ERP sin tipo de cambio trazable, así que también escala. Las
anotaciones manuscritas, importes tachados/corregidos, campos contradictorios,
IBAN fuera de maestro y texto que intenta dar instrucciones bloquean `PAGAR`.
La única excepción segura a una moneda ausente es `NO_PAGAR` cuando el pedido
e identidad están verificados y el asiento ERP más reciente, único y
consistente ya figura como `PAGADA`; no se mueve dinero.

La norma v3 está implementada en `factu/policy.py` y configurada en `factu/policies/v3.json`. Los criterios de `NO_PAGAR` son decisiones explícitas del equipo, no reglas supuestamente publicadas por Maisa. El checksum del IBAN se conserva como diagnóstico, pero no bloquea: los IBAN sintéticos del maestro fallan ese checksum. La regla del reto es la igualdad con el maestro.

## Lectura con modelo (tercer método)

Las mediciones de esta sección son **históricas del `main` anterior** (extractor `native-rapidocr-modelo-2`). No se han repetido en 0.9.2. Esta integración conserva moneda ausente como MISSING y añade histórico de pedidos, por lo que esos repartos no describen las decisiones actuales. Las pruebas del proveedor en esta integración usan respuestas simuladas, sin llamadas facturables. El reparto vigente sin modelo externo es 435/9/56 (ver Cifras vigentes).

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

En «Consultas a proveedores» se muestran solo dudas externas permitidas por reglas explícitas. Seguridad, identidad incierta, contabilidad y cambios bancarios se revisan internamente. El borrador es editable, copiable y descargable; nunca se envía desde la app. Solo la moneda admite confirmación compartida: respuesta verificada, referencia, autor, facturas seleccionadas, vista previa y confirmación. Cada expediente se recalcula sin aprobar pagos. Importes, IBAN, fechas y referencias se revisan individualmente. Autor escrito no equivale a identidad autenticada: esta versión es local, de operador único.

## Cuando cambia una fuente

En «Datos y actualizaciones», carga un Excel/reglas o pulsa «Actualizar datos del ERP». «Ver facturas afectadas» compara sin aplicar: distingue resultados que se mantienen, pasan a revisión o cambian de otra forma, y decisiones reutilizadas. «Revisar cambios» permite ver cada factura antes de «Aplicar actualización». La nota y el nombre son opcionales; sin nombre se registra «Sesión local (sin identificar)», no una identidad autenticada. Un cambio de reglas requiere confirmación expresa, también si una nueva norma viene dentro del Excel. No se convierte texto libre en reglas automáticamente.

Los cambios del ERP se comparan por pedido; los del maestro por proveedor/pedido/norma. Una dependencia desconocida invalida conservadoramente. Una nueva política o versión de código puede afectar a todo el lote. Cero repeticiones de OCR en estos cambios. Si se interrumpe tras aplicar la fuente, las decisiones afectadas quedan pendientes y se recuperan con «Reevaluar».

Una previsualización ERP fallida conserva la fuente vigente y registra el error: no se ha aplicado el cambio. «Sincronizar ERP completo», en cambio, refresca el lote completo e invalida resultados si falla. La interfaz distingue ambas operaciones.

## Lote 2 y cambios de norma

Lote 2 ya usa el comando dedicado descrito arriba. El runner valida los límites
del reto a propósito: 500 PDFs en Lote 1 y 40 en Lote 2; ambos conservan
snapshot, política y perfil de extracción propios. Los duplicados se vuelven a
calcular entre lotes antes de publicar decisiones.

Una norma v4 futura **no** se interpreta automáticamente con un LLM ni se
puede pasar hoy como `--policy` al comando `lote2`. El flujo correcto es:

1. Guardar el texto/fichero original como una fuente versionada y documentar la
   diferencia de negocio.
2. Implementar explícitamente la semántica nueva y sus pruebas; por ejemplo,
   una política FX necesita moneda nativa, tipo de cambio fechado, fuente
   autorizada y reglas de redondeo.
3. Crear un JSON de política válido solo cuando el código represente esa
   semántica y un responsable lo haya revisado.
4. Aplicar la política al lote correspondiente y enseñar la previsualización de
   impacto antes de confirmar.

El adaptador Excel espera `Proveedores`, `Pedidos_2026`, `Norma_Pagos_v3` y las
columnas del libro inicial; Lote 2 añade adaptadores explícitos para los dos
CSV incrementales. Si cambia ese esquema, adapta `master.py` con tests antes de
importar. Versionar una política no afirma compatibilidad automática con una
norma desconocida.

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

El plan actualizado de esta versión está en `docs/albertitos_plan.pdf`, con
arquitectura y ADRs; revisadlo junto con el nuevo
`docs/RELEASE-v0.10.0.md` antes de entregar. Sustituye como referencia al
borrador de propuesta anterior del chat. Lote 2 ya se procesa localmente con
materiales oficiales, pero el JSONL de entrega se exporta desde el estado
auditado que vaya a presentarse, no se versiona un resultado estático en el
código. La auditoría de materiales está en `docs/MATERIALS.md` y el estado de
cumplimiento en `docs/COMPLIANCE.md`.

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
