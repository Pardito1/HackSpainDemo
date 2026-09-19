# FactU en GitHub

El repositorio compartido es `Pardito1/HackSpainDemo`. La app está en `factu-control/`; no muevas su contenido a la raíz ni borres los módulos de tus compañeros.

## Actualizar tu copia

Con el trabajo local guardado en un commit o respaldado:

```bash
git switch main
git pull --ff-only
cd factu-control
source .venv/bin/activate
python -m pip install -e '.[ocr,test]'
python -m pytest -q
```

Si Git avisa de divergencias o cambios locales, no uses `reset --hard` ni `push --force`. Revisa e integra ese trabajo. Para Windows usa Ubuntu/WSL2 y su propio entorno virtual.

Conserva tu carpeta de estado y haz una copia con la app parada. Git no incluye las bases de datos, las credenciales, las sesiones ni los entornos virtuales. Consulta [la actualización 0.9.2](docs/RELEASE-v0.9.2.md) antes de reprocesar una versión anterior.

## Qué contiene cada parte

- `factu-control/`: código, interfaz, pruebas y documentación de la app.
- `500-sombras-de-alberto-main/`: materiales oficiales que el equipo ya incorporó; se conservan.
- `pipeline/`, `main.py`, `tests/`, `outputs/`: prototipo anterior, no el motor de la web.
- `referencia/`: referencias del equipo, sin sobrescribirlas con nuevos resultados.
- `entrega-parcial-v0.9.1/`: 500 resultados y plan históricos. No es una entrega final ni una ejecución del motor integrado.

El script `scripts/package.py` genera un ZIP solo de la app (sin materiales ni estado), con manifiesto SHA-256. El PDF en `docs/albertitos_plan.pdf` describe la ejecución local 0.9.1; la arquitectura integrada con modelo opcional está en `docs/ARCHITECTURE.md`.

## Verificar antes de publicar cambios

```bash
python -m pytest -q
node --test tests/test_frontend.mjs
git diff --check
git status --short
```

Node solo es necesario para las pruebas JavaScript. Revisa lo preparado para commit: no debe incluir `.env`, tokens, bases SQLite, sesiones, datos de clientes ajenos al reto o carpetas de estado. Las claves del modelo se configuran fuera de Git.

Subir el código a GitHub **no despliega la web**. Esta versión local no tiene autenticación de producción: no la expongas directamente a Internet.

## Entrega del concurso: otro repositorio

Su raíz debe contener exclusivamente:

```text
outcomes.jsonl
outcomes_lote2.jsonl
albertitos_plan.pdf
```

Faltan las 40 facturas oficiales del segundo lote y sus resultados. No uses una copia del primer lote ni un archivo vacío para sustituirlo. Las nuevas reglas del Excel v8 de prueba tampoco están implementadas por marcar una casilla: debe comprobarse y actualizarse la política ejecutable antes de aplicarlas.
