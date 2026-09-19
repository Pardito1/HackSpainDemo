# Procesar las 500 facturas reales · v0.9.2

Actualización 0.9.2: se conserva la carpeta `factu-control` del equipo y los comandos `python -m factu`. El lector integrado tiene una nueva versión de caché; si necesitas aplicar sus cambios a lecturas anteriores, sigue [la actualización con copia de seguridad](docs/RELEASE-v0.9.2.md). Los resultados al final de esta guía son históricos de 0.4, no del motor integrado.

Si ya tenías las 500 procesadas con una versión anterior, conserva tu carpeta de estado. Arranca la versión nueva con esa misma carpeta y vuelve a cargar el Excel original en **Datos y actualizaciones → Ver facturas afectadas → Aplicar actualización**. Así se incorpora `Pedidos_2025_OLD` sin repetir OCR ni borrar el historial. Reanudar `lote1` por sí solo no vuelve a importar un Excel ya registrado.

No ejecutes `make_demo.py`: solo crea cuatro facturas de prueba. El estado de la demo no contiene las 500 originales. Subir el código a GitHub tampoco sube ni crea la base de datos de cada compañero.

## Carpetas

Estos comandos se ejecutan dentro de `factu-control`, con esta estructura:

```text
HackSpainDemo/
  factu-control/                 <- terminal aquí
  500-sombras-de-alberto-main/
    alberto_erp.py
    FINAL_v7_DEFINITIVO_ahorasi.xlsx
    facturas/                     <- 500 PDF oficiales
```

Si tu carpeta oficial se llama `500-sombras-de-alberto` (sin `-main`), cambia ese nombre en los comandos. No mezcles el lote de 40 con `facturas/`; se importa como otro lote mediante el flujo general del README.

## Mac

Necesitas Python 3.11 o superior; se ha probado Python 3.12. Comprueba `python3 --version`.

Terminal 1, dentro de `factu-control` (déjala abierta):

```bash
python3 ../500-sombras-de-alberto-main/alberto_erp.py
```

Si ya está funcionando el ERP **oficial** en 8009, no arranques otro. No uses `scripts/demo_erp.py`.

Terminal 2, también dentro de `factu-control`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[ocr,test]'
python -m factu --data estado-500-v04 lote1 --materials ../500-sombras-de-alberto-main --as-of 2026-09-19 --url http://127.0.0.1:8009 --serve --port 8089
```

Se descargan dependencias durante la instalación. Texto y OCR son locales; si configuras credenciales del método `modelo`, se enviarán al proveedor las páginas escaneadas que queden sin resolver. Sin claves no se usa ese proveedor. Espera al mensaje de 500 resultados únicos. Abre **http://127.0.0.1:8089/**, no la antigua pestaña 8087. El programa también imprime el enlace al lote concreto.

## Windows

Esta versión utiliza `fcntl`: ejecútala en **Ubuntu con WSL2**, no directamente en PowerShell ni CMD. WSL2 no se ha probado en este equipo.

Si no tienes WSL2, instala Ubuntu desde PowerShell como administrador y sigue las indicaciones de Windows:

```powershell
wsl --install -d Ubuntu
```

Después abre Ubuntu, entra en `factu-control` (las unidades de Windows aparecen en `/mnt/c/`) e instala los componentes del sistema si faltan:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libgl1 libglib2.0-0
```

Comprueba `python3 --version` (3.11 o superior). Sigue **los mismos dos bloques de terminal de Mac**, pero en dos terminales de Ubuntu. El entorno `.venv` debe crearse dentro de WSL; no reutilices uno de Windows. Abre http://127.0.0.1:8089/ en el navegador de Windows.

## Qué hace el comando

1. Comprueba 500 PDFs con nombres únicos y el Excel oficial.
2. Los importa a `estado-500-v04`, sin modificar originales ni mezclar la demo.
3. Descarga todo el ERP por HTTP, con sesión, paginación y reintentos. Rechaza un ERP diminuto como el de demo.
4. Lee las 500 facturas, con OCR cuando hace falta; luego publica las decisiones con comprobación de duplicados. Durante la lectura puede haber 0 decisiones: verás avanzar el contador de **leídas**.
5. Verifica 500 resultados únicos y la integridad de la auditoría; arranca la web con esa misma carpeta de estado.

Si se interrumpe, vuelve a ejecutar el mismo comando: comprueba el manifiesto y reutiliza el avance sin crear otro lote. Una tarea interrumpida en ejecución puede conservar su reserva hasta 10 minutos; espera si el programa lo necesita. Si el estado pertenece a una demo/otro lote/otra versión del lector, usa una carpeta `--data` nueva. No borres la anterior.

## Volver a abrir sin reprocesar

Desde `factu-control`, con el entorno activado:

```bash
export ERP_URL=http://127.0.0.1:8009
python -m factu --data estado-500-v04 serve --port 8089
```

El ERP solo necesita estar encendido si quieres volver a consultar datos contables. Usa siempre la misma carpeta `--data`; otra carpeta abre otra base de datos. Si aparece un filtro «Propuesta de pago», elige «Todas» o «Quitar filtros».

## Qué significan los ceros

- **0 pendientes de procesar** es correcto cuando las 500 ya tienen resultado.
- **0 resultados en una búsqueda** no significa que no haya facturas: revisa los filtros.
- **0 € de gasto externo**, en el área técnica, es correcto sin APIs de pago. No incluye el coste del ordenador ni el tiempo humano.
- **Moneda no indicada** no se convierte en EUR: pide confirmación y regístrala, con autor y motivo. La app distingue un dato leído de uno confirmado por una persona.

Prueba local 19/09/2026, primer lote y ERP oficial: **273 PAGAR, 9 NO_PAGAR, 218 ESCALAR; 500 resultados y 0 pendientes**. La distribución puede cambiar con una política, datos o revisiones diferentes. No es una medición de exactitud ni garantiza APTO del concurso.

El ZIP es de código: no contiene el estado, las 500 facturas ni el ERP oficial. No subas `estado-500-v04` a GitHub. El repositorio de entrega del concurso es independiente y contiene únicamente los dos JSONL y `albertitos_plan.pdf` exigidos.
