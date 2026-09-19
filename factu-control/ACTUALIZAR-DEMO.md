# Poner en marcha la demo corregida · v0.3.1

La versión anterior escribía la misma instrucción maliciosa en las tres facturas. El motor las enviaba a consulta. Ahora hay cuatro casos separados y el ERP sintético contiene sus cuatro pedidos.

## Si ya tenías la versión anterior

1. En las terminales de la aplicación y del ERP **de demo**, pulsa `Ctrl+C` para detenerlos.
2. Descomprime el ZIP nuevo en una carpeta nueva y abre una terminal dentro de `factu-control`. Así conservas el código y el estado anteriores.
3. En macOS, o en Ubuntu dentro de WSL2 en Windows, prepara el entorno:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
```

Si no existe una dependencia fijada compatible con tu plataforma, instala las declaradas para ella:

```bash
python -m pip install -e '.[ocr,test]'
```

Esta versión mantiene el requisito de WSL2 en Windows. No reutilices un entorno virtual creado en otro sistema operativo.

## Terminal 1: documentos nuevos y ERP actualizado

Dentro de la carpeta nueva, con el entorno activado:

```bash
python scripts/make_demo.py --output demo-input-v031
python scripts/demo_erp.py
```

Debe anunciar **v0.3.1 · 4 pedidos** en el puerto 8019. Deja la terminal abierta. Si dice que el puerto está ocupado, comprueba si sigue abierta la terminal del ERP de demo antiguo y detenla con `Ctrl+C`.

## Terminal 2: importar, comprobar y abrir

Abre otra terminal en la misma carpeta nueva `factu-control`:

```bash
source .venv/bin/activate
export ERP_URL=http://127.0.0.1:8019

python -m factu --data demo-state-v031 ingest \
  --pdfs demo-input-v031/facturas \
  --excel demo-input-v031/maestro.xlsx \
  --name "Demo sintética v0.3.1" \
  --as-of 2026-09-19
```

Copia el `batch_id` que devuelve y sustitúyelo en los tres comandos siguientes:

```bash
python -m factu --data demo-state-v031 sync-erp ID_DEL_LOTE
python -m factu --data demo-state-v031 process ID_DEL_LOTE
python -m factu --data demo-state-v031 serve --port 8080
```

Abre [http://127.0.0.1:8080](http://127.0.0.1:8080) sin los filtros de una URL antigua. Comprueba que el pie de la app indica **v0.3.1**. Si el puerto 8080 está ocupado por otra aplicación, usa `--port 8081` y abre ese puerto.

## Lo que debes ver

| Factura | Resultado | Motivo |
| --- | --- | --- |
| demo-1.pdf | PAGAR | Controles correctos |
| demo-2.pdf | ESCALAR | IBAN distinto del maestro |
| demo-3.pdf | NO_PAGAR | Pedido ya pagado en ERP |
| demo-4.pdf | ESCALAR | Instrucción engañosa; los otros controles pasan |

Totales: **4 facturas, 1 propuesta de pago, 1 no pagar, 2 consultas y 0 pendientes de procesar**.

## Por qué antes veías ceros

- **0 propuestas y 0 no pagar:** las tres facturas antiguas contenían la instrucción engañosa y estaban en consulta.
- **0 en la tabla:** estaba seleccionado «Propuesta de pago», que no tenía coincidencias. Ahora la cabecera indica el filtro y aparece «Mostrando X de Y facturas» junto a «Quitar filtros».
- **0 pendientes de procesar:** el procesamiento ya había terminado; las consultas humanas se cuentan aparte.
- **0,00 € en proveedores externos:** se usa OCR local y no hay llamadas de pago. El tiempo humano y el equipo no están valorados en ese contador.
- **3 o 4 facturas en lugar de 500:** has cargado datos sintéticos. El ZIP no contiene las 500 facturas oficiales ni la base de datos de otro ordenador.

Reprocesar los PDFs antiguos no quita la frase: primero hay que generar e importar los nuevos. Los comandos de arriba utilizan carpetas nuevas y conservan la demo antigua. Si vuelves a ejecutar la generación sobre un directorio existente, el script lo rechazará; usa otro nombre coherente en todos los comandos.

## Actualizar GitHub

Actualiza los archivos de la carpeta `factu-control` con el contenido de esta versión, conserva los datos de trabajo fuera de Git y revisa los cambios antes del commit. No subas `.venv`, `demo-input-v031` ni `demo-state-v031`. El ZIP incluye un `.gitignore` actualizado y `GITHUB.md` con el procedimiento.
