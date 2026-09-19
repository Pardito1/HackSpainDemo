"""Bundle source/docs/tests only, never runtime state, credentials or challenge data."""

import argparse
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    chosen = [
        root / name
        for name in ("README.md", "GITHUB.md", "ACTUALIZAR-DEMO.md", "PROCESAR-500.md", "pyproject.toml", "requirements.lock", ".gitignore")
    ]
    extensions = {".py", ".md", ".html", ".css", ".js", ".mjs", ".json", ".pdf", ".svg"}
    # Las etiquetas y el informe del Lote 2 forman parte de la evidencia de
    # evaluación: incluirlos permite repetir la métrica publicada sin
    # empaquetar datos de ejecución, credenciales ni PDFs del reto.
    for folder in ("factu", "docs", "tests", "scripts", "evaluacion"):
        chosen.extend(
            p
            for p in (root / folder).rglob("*")
            if p.is_file() and p.suffix in extensions and "__pycache__" not in p.parts
        )
    target = Path(args.output)
    if target.exists():
        parser.error(
            "El ZIP ya existe; usa otro nombre para conservar la versión anterior"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    hashes = []
    with ZipFile(target, "x", compression=ZIP_DEFLATED) as archive:
        for path in sorted(chosen):
            relative = path.relative_to(root).as_posix()
            content = path.read_bytes()
            archive.writestr("factu-control/" + relative, content)
            hashes.append(hashlib.sha256(content).hexdigest() + "  " + relative)
        archive.writestr("factu-control/MANIFEST.sha256", "\n".join(hashes) + "\n")
    (root / "MANIFEST.sha256").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    with ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP corrupto")
    print(
        f"{target}: {len(chosen)} archivos + manifiesto; {target.stat().st_size} bytes"
    )
    print("SHA-256 " + hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
