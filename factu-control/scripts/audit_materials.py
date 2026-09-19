"""Read-only comparison of supplied materials and the files actually ingested."""
import argparse
import hashlib
import json
from pathlib import Path
from factu.service import Service


def audit(source, service, batch):
    source = Path(source)
    manifest = json.loads((Path(__file__).parents[1] / "factu/materials.json").read_text())
    files = []
    for item in manifest["files"]:
        path = source / item["name"]
        value = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        files.append({"file": item["name"], "sha256": value, "matches_reviewed": value == item["sha256"]})
    originals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source / "facturas").rglob("*.pdf")}
    documents = service.store.all("SELECT file_id,sha256,extraction,latest_decision,path FROM documents WHERE batch_id=?", (batch,))
    mismatches = [d["file_id"] for d in documents if originals.get(d["file_id"]) != d["sha256"] or hashlib.sha256(Path(d["path"]).read_bytes()).hexdigest() != d["sha256"]]
    missing = sorted(set(originals) - {d["file_id"] for d in documents})
    master = service.store.source(service.batch(batch)["master_id"])
    return {"files": files, "pdfs_supplied": len(originals), "pdfs_ingested": len(documents),
            "pdfs_extracted": sum(bool(d["extraction"]) for d in documents),
            "current_decisions": sum(bool(d["latest_decision"]) for d in documents),
            "missing": missing, "hash_mismatches": mismatches,
            "master_sha256": master["sha256"], "sheets": master["sheets"],
            "supplier_rows": sum(len(v) for v in master["suppliers"].values()),
            "supplier_ids": len(master["suppliers"]), "orders": len(master["orders"]),
            "audit": service.store.verify_audit()}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--batch", required=True)
    p.add_argument("--report")
    args = p.parse_args()
    report = audit(args.source, Service(args.data), args.batch)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    print(text)
