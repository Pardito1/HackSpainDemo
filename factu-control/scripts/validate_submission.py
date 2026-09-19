"""Validate the public deliverable contract, NOT the organizer's private labels."""

import argparse
import json
import sys
from pathlib import Path
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factu.utils import file_name  # noqa: E402


def check_jsonl(path, pdfs):
    # macOS lista los nombres con tilde en NFD y el reto los publica en NFC:
    # las dos listas se comparan en la misma forma o los 65 acentuados fallan.
    originals = [
        file_name(p.name)
        for p in Path(pdfs).rglob("*")
        if p.is_file() and p.suffix.lower() == ".pdf"
    ]
    if not originals or len(set(originals)) != len(originals):
        raise ValueError("Manifiesto vacío o nombres PDF duplicados")
    ids = []
    for number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            raise ValueError(f"{path.name}:{number}: línea vacía")
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("file_id"), str)
            or row.get("result") not in {"PAGAR", "NO_PAGAR", "ESCALAR"}
        ):
            raise ValueError(f"{path.name}:{number}: contrato inválido")
        ids.append(row["file_id"])
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name}: file_id duplicado")
    if set(ids) != set(originals):
        raise ValueError(
            f"{path.name}: faltan {len(set(originals)-set(ids))}; sobran {len(set(ids)-set(originals))}"
        )
    return len(ids)


def validate(folder, lote1, lote2):
    folder = Path(folder)
    expected = {"outcomes.jsonl", "outcomes_lote2.jsonl", "albertitos_plan.pdf"}
    files = {p.name for p in folder.iterdir() if p.name != ".git"}
    if files != expected:
        raise ValueError(
            f"La raíz debe contener exactamente {sorted(expected)} además de .git"
        )
    counts = [
        check_jsonl(folder / "outcomes.jsonl", lote1),
        check_jsonl(folder / "outcomes_lote2.jsonl", lote2),
    ]
    with pymupdf.open(folder / "albertitos_plan.pdf") as pdf:
        if pdf.needs_pass or len(pdf) == 0:
            raise ValueError("Plan protegido o vacío")
    return {
        "contract_valid": True,
        "documents": counts,
        "warning": "No comprueba la referencia privada ni concede APTO. Revisar visualmente el plan y confirmar plazo oficial.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder")
    p.add_argument("--lote1", required=True)
    p.add_argument("--lote2", required=True)
    args = p.parse_args()
    try:
        print(
            json.dumps(
                validate(args.folder, args.lote1, args.lote2),
                ensure_ascii=False,
                indent=2,
            )
        )
    except (ValueError, OSError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
