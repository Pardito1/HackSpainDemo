# FactU 0.9.0 — importes y tolerancia a fallos

Comprobación realizada el 19/09/2026. No se han modificado facturas, Excel ni datos del ERP, ni se han creado aprobaciones humanas para hacer pasar las pruebas.

## Correcciones

- El OCR podía juntar base e IVA y asignar a la base el último importe de la línea. Ahora separa las etiquetas, incluidos los casos `1VA`, y no sustituye un número dañado por otro posterior. Se conserva el texto leído como evidencia.
- Se admiten miles separados por espacios y signos negativos explícitos. Una lectura ambigua, un porcentaje confundido con importe o un separador decimal perdido no se adivinan.
- Los errores de conexión, protocolo, XML, paginación y cabeceras Retry-After inválidas se capturan. Un fallo deja el documento en `ERP_ERROR`, con motivo y fecha; reprocesar no borra ese estado.
- Un snapshot incompleto nunca se publica. Se conservan originales, lecturas, revisiones y decisiones históricas. Se impide exportar resultados desactualizados.
- Recuperación: hasta cinco intentos acotados por petición en producción (timeout de 10 segundos, espera creciente con dispersión). XML inválido requiere nueva sincronización. Si se agotan los intentos, el operador actualiza el ERP y vuelve a procesar; no existe un trabajador indefinido en segundo plano.
- Se corrige el percentil 95 al criterio de rango más próximo. La calculadora de costes rechaza negativos, infinitos y desbordamientos.
- Consultas a proveedores aclara el solapamiento con revisiones internas: 173 consultas y 47 revisiones internas incluyen 4 facturas compartidas; son 216 distintas, no 220. Los 31.303,20 EUR de importes declarados conocidos excluyen 166 facturas sin importe o moneda confirmados; no son deuda validada.
- Motivos de revisión/no pago y avisos importantes aparecen en amarillo fluorescente. Un aviso específico diferencia una lectura de un importe confirmado cuando no se pueden validar las sumas.

## Resultado del lote disponible

500 originales cotejados por hash; 500 expedientes accesibles; 14 hojas del Excel accesibles; 500 resultados únicos. Se reprocesó con extracción `native-rapidocr-6`.

- 275 propuestas de pago, 9 no pagar, 216 requieren revisión; 0 pendientes de procesar.
- Los detalles de las 471 facturas con texto nativo suman su base. Las otras 29 son escaneadas: no se certifica la exactitud de cada cifra del OCR.
- IVA: 481 comprobaciones coinciden, 7 discrepan, 12 no tienen datos suficientes.
- Base + IVA = total: 481 coinciden, 4 discrepan, 15 no tienen datos suficientes.
- Total contra ERP: 469 coinciden, 14 discrepan, 17 no se pueden comprobar con seguridad.
- Los conjuntos se solapan: 25 facturas tienen alguna suma discrepante o indeterminada y todas requieren revisión. No son 25 errores demostrados del documento: incluyen problemas de lectura.
- Los importes de los 516 pedidos del Excel y ERP coinciden: 2.638.495,71. Esto es una suma de registros de pedidos, no dinero aprobado ni suma de las 500 facturas.
- Persisten 17 contradicciones de identificador de proveedor entre Excel y ERP. No se resuelven inventando una prioridad.
- Las hojas ajenas a la decisión contienen `NO_TOCAR!A1 =SUMA(#REF!)` sin resultado almacenado y `MACROS_ROTAS!A2 #REF!`. Se conservan, no se ejecutan ni se usan para aprobar.

## PDF de tolerancia a fallos: verificaciones realizadas

197 pruebas Python y 10 JavaScript superadas. Siete advertencias de deprecación de dependencias; ninguna prueba fallida. Seis escenarios con HTTP local real y datos sintéticos aislados: timeout, ERP apagado, XML inválido, HTTP 500, HTTP 429 y fallo después de recibir la primera página.

| Punto del PDF | Evidencia comprobada |
| --- | --- |
| Provocar y capturar un fallo | Seis escenarios; evento `erp_sync_failed` con fecha y motivo |
| Conservar el estado | `WAITING_ERP → ERP_ERROR`; mismo original y misma extracción en SQLite |
| No volver a pendiente | Un reprocesado durante el fallo mantiene `ERP_ERROR` |
| Evitar trabajo concurrente | Otro proceso queda bloqueado mientras hay trabajo activo |
| No duplicar salidas | Una línea por archivo; otro reintento no añade decisiones ni líneas |
| Duplicados entre lotes | La repetición no genera otra propuesta pagable: PAGAR / NO_PAGAR |
| Recuperar tras reinicio | Nueva instancia del servicio, sincronización correcta, `DECIDED` y trabajo `DONE` |
| Conservar el OCR | Un solo intento de extracción; no se repite durante la recuperación |
| Trazabilidad | Cadena válida; consulta SQL, checkpoints y eventos exportables con timestamp |
| Demo | La prueba `offline` ejecuta la secuencia de siete pasos del PDF |

Cada lote debe seguir teniendo un registro por archivo aunque el documento esté repetido en otro lote: se bloquea el segundo pago, no se suprime la salida exigida por el contrato del concurso. Los tests usan timeout de 0,08 segundos y tres intentos para ser rápidos; no se presentan como mediciones del ERP oficial.

### Repetir las pruebas y guardar evidencia

Con dependencias de desarrollo instaladas, en macOS o Windows con WSL2:

```bash
python -m pytest -q
node --test tests/test_frontend.mjs
FACTU_QA_OUTPUT=qa-evidence python -m pytest -q tests/test_provider_checklist.py
```

Se crean `verificacion.json`, `trazabilidad.jsonl` y un `outcomes.jsonl` sintético por escenario. No los confundas con los resultados oficiales. Usa una carpeta nueva para conservar evidencias anteriores.

### Guion de defensa, unos tres minutos

1. Ejecuta `FACTU_QA_OUTPUT=qa-demo python -m pytest -q tests/test_provider_checklist.py -k 'all_provider_failure_steps and offline'`.
2. Abre `qa-demo/offline/verificacion.json`: muestra el checkpoint inicial, la lectura guardada y después `ERP_ERROR` con fecha y motivo.
3. Señala `no_output_during_failure: true`: no se permite exportar durante el fallo.
4. Muestra el checkpoint final tras restaurar el proveedor y crear otra instancia: documento `DECIDED`, trabajo `DONE`, mismo OCR.
5. Abre `outcomes.jsonl`: una sola línea. Muestra la consulta SQL sin duplicados y la repetición entre lotes, no pagable por segunda vez.
6. Abre `trazabilidad.jsonl` para seguir los intentos y la recuperación. Aclara que es una prueba controlada local, no una caída provocada del ERP de la organización.

## Actualizar conservando el trabajo

Detén la app y copia toda tu carpeta de datos. Usa la nueva versión con esa misma carpeta. A diferencia de 0.8.0, es necesario repetir la extracción para aplicar el arreglo del parser:

```bash
python -m factu --data RUTA_DE_DATOS verify-audit
python -m factu --data RUTA_DE_DATOS batches
python -m factu --data RUTA_DE_DATOS reextract ID_DEL_LOTE
python -m factu --data RUTA_DE_DATOS process ID_DEL_LOTE
python -m factu --data RUTA_DE_DATOS verify-audit
python -m factu --data RUTA_DE_DATOS serve --port 8089
```

Si no existe una consulta ERP completa, ejecuta primero `sync-erp ID_DEL_LOTE`. Sustituye las rutas e ID por los tuyos; no borres la base de datos ni los originales. Las revisiones anteriores permanecen, pero una aprobación puede caducar si cambia su contexto. En esta actualización las 500 facturas se han vuelto a leer sin introducir respuestas humanas ficticias.

## Límites

Estas pruebas no demuestran precisión del 100 %, ausencia universal de bugs, aprobación del verificador privado ni revisión del lote 2, todavía no disponible en los materiales auditados. Windows nativo no está soportado: utiliza WSL2. La app es local, no autentica al revisor y no mueve dinero. Un coste externo de 0 € significa que no se han usado APIs de pago, no que el ordenador o la revisión humana sean gratuitos. El PDF de arquitectura incluido es histórico; revisadlo junto con estas notas antes de la entrega final.
