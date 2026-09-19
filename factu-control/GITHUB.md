# Subir FactU Control a GitHub

## Qué subir

Descomprime el ZIP. Entra en la carpeta `factu-control` y usa **su contenido** como raíz del repositorio: el README debe aparecer directamente en la portada, no dentro de otra carpeta.

Incluye código Python, interfaz HTML/CSS/JavaScript, dependencias fijadas, pruebas Python/JavaScript, demo sintética, scripts y documentación. El PDF de arquitectura está en `docs/albertitos_plan.pdf`.

No incluye datos oficiales del reto, el ERP de terceros, base de datos de trabajo, entornos virtuales, sesiones ni credenciales personales. Se conservan únicamente los valores sintéticos públicos del ERP de demostración, identificados como tales en el README. Para ejecutar sin los materiales oficiales, utiliza la demo de tres facturas descrita en el README; para las 500 originales, descarga el paquete del organizador por separado.

El revisor generativo de IA comentado como posible mejora **no está implementado**. La versión 0.3 incluye OCR neuronal local, reglas deterministas y revisión humana.

## Pasos

1. Crea un repositorio vacío en GitHub. No inicialices allí otro README ni `.gitignore`. Elige su visibilidad; privado es suficiente para colaborar con el equipo.
2. Abre una terminal dentro de la carpeta descomprimida `factu-control`.
3. Ejecuta:

```bash
git init -b main
git add .
git status --short
git diff --cached --stat
```

4. Revisa los archivos preparados. No deben aparecer bases de datos, datos de clientes, `.env`, sesiones o claves. `.gitignore` evita los casos habituales, pero no sustituye esta revisión si has añadido archivos por tu cuenta.
5. Guarda el primer commit:

```bash
git commit -m "FactU Control v0.3: app, pruebas y documentación"
```

6. Copia de GitHub la URL real del repositorio. Sustituye `URL_DE_TU_REPOSITORIO` y publica:

```bash
git remote add origin URL_DE_TU_REPOSITORIO
git push -u origin main
```

Estos pasos no se han ejecutado por ti: el ZIP está preparado, pero no se ha publicado ningún repositorio.

## Instalación y comprobación

Sigue el README para crear el entorno e instalar las dependencias. Dentro del entorno:

```bash
python -m pytest -q
node --test tests/test_frontend.mjs
```

Node solo es necesario para las pruebas JavaScript. La app funciona con Python y sirve su interfaz sin compilación de frontend. Los paquetes y modelos OCR se instalan por separado; no se incluyen en el ZIP. Consulta compatibilidad y límites en el README.

Subir el código a GitHub **no despliega la web**. Esta versión está diseñada para ejecutarse en local y no tiene autenticación de producción: no la expongas directamente a Internet.

## Importante: no confundir con la entrega del concurso

El repositorio de resultados debe ser **otro repositorio**, con exactamente estos tres archivos en la raíz:

```text
outcomes.jsonl
outcomes_lote2.jsonl
albertitos_plan.pdf
```

Los JSONL se generan después de procesar y revisar ambos lotes. No se incluye un resultado inventado para el segundo lote pendiente. El PDF actual documenta la versión 0.3; actualízalo si cambian datos, reglas o arquitectura antes de entregar.

No se añade una licencia elegida arbitrariamente para vuestro código. El equipo debe decidirla si desea conceder permisos de reutilización; las dependencias conservan sus propias licencias.
