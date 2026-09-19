"""Local integrity checks, not an external signature or administrator-proof ledger."""
import json
from pathlib import Path

from .utils import digest


def verify(store):
    tables = ("events", "sources", "documents", "decisions", "reviews", "human_decisions", "extraction_cache")
    # One read transaction prevents a concurrent commit appearing half-published.
    with store.connect() as db:
        db.execute("BEGIN")
        rows = {t: [dict(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY id")] for t in tables}
    indexes = {t: {r["id"]: r for r in data} for t, data in rows.items()}
    issues, warnings = [], []
    head = "0" * 64
    anchors, extraction_hashes, manifests, published, current_published = {}, {}, {}, {}, {}

    def issue(kind, target):
        issues.append({"kind": kind, "target": str(target)})

    for row in rows["events"]:
        try:
            payload = json.loads(row["payload"])
            body = {k: row[k] for k in ("kind", "document_id", "batch_id", "created", "prev_hash")}
            body["payload"] = payload
            if row["prev_hash"] != head or digest(body) != row["hash"]:
                issue("event_chain", row["id"])
            head = row["hash"]
            for anchor in payload.get("_records", []):
                anchors[(anchor["table"], anchor["id"])] = anchor
            if row["kind"] == "extracted" and payload.get("extraction_sha256"):
                extraction_hashes[row["document_id"]] = payload["extraction_sha256"]
            if row["kind"] == "batch_ingested":
                for entry in payload["manifest"]:
                    manifests[(row["batch_id"], entry["file_id"])] = entry["sha256"]
            if row["kind"] == "decision_published":
                published[payload["decision_id"]] = (row["document_id"], payload["context_hash"], payload["result"])
                current_published[row["document_id"]] = payload["decision_id"]
        except (ValueError, KeyError, TypeError, AttributeError):
            issue("event_structure", row["id"])
    chain_valid = not issues

    for (table, record_id), anchor in anchors.items():
        record = indexes.get(table, {}).get(record_id)
        if record is None:
            issue("missing_record", f"{table}:{record_id}")
        else:
            selected = {k: record.get(k) for k in anchor["columns"]}
            if digest(selected) != anchor["sha256"]:
                issue("record_changed", f"{table}:{record_id}")

    for row in rows["sources"]:
        try:
            payload = json.loads(row["payload"])
            if digest({"kind": row["kind"], "payload": payload}) != row["id"]:
                issue("source_changed", row["id"])
            if payload.get("blob"):
                path = Path(payload["blob"])
                if not path.is_file() or digest(path.read_bytes()) != payload["sha256"]:
                    issue("source_file_changed", row["id"])
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            issue("source_unreadable", row["id"])

    for row in rows["decisions"]:
        try:
            payload = json.loads(row["payload"])
            expected = digest({k: v for k, v in payload.items() if k != "context_hash"})
            if (expected != row["context_hash"] or payload.get("context_hash") != expected
                    or payload.get("result") != row["result"]
                    or published.get(row["id"]) != (row["document_id"], expected, row["result"])):
                issue("decision_changed", row["id"])
        except (ValueError, TypeError, AttributeError):
            issue("decision_unreadable", row["id"])
    for decision_id in published:
        if decision_id not in indexes["decisions"]:
            issue("missing_decision", decision_id)

    found_manifest = set()
    for row in rows["documents"]:
        key = (row["batch_id"], row["file_id"])
        found_manifest.add(key)
        if manifests.get(key) != row["sha256"]:
            issue("document_manifest", row["id"])
        try:
            if digest(Path(row["path"]).read_bytes()) != row["sha256"]:
                issue("document_file_changed", row["id"])
            if row["extraction"]:
                actual = digest(json.loads(row["extraction"]))
                if row["id"] in extraction_hashes:
                    if actual != extraction_hashes[row["id"]]:
                        issue("extraction_changed", row["id"])
                else:
                    warnings.append({"kind": "legacy_extraction_unsealed", "target": row["id"]})
        except (ValueError, TypeError, OSError):
            issue("document_unreadable", row["id"])
        if row["latest_decision"] is not None:
            decision = indexes["decisions"].get(row["latest_decision"])
            if (decision is None or decision["document_id"] != row["id"]
                    or current_published.get(row["id"]) != row["latest_decision"]):
                issue("decision_pointer", row["id"])
    for key in manifests.keys() - found_manifest:
        issue("missing_document", key)
    for table in ("reviews", "human_decisions"):
        for row in rows[table]:
            if (table, row["id"]) not in anchors:
                warnings.append({"kind": "legacy_record_unsealed", "target": f"{table}:{row['id']}"})
    # Orphaned originals/caches remain evidence even when superseded.
    checked_blobs = 0
    for path in (store.root / "blobs").iterdir():
        if not path.is_file():
            continue
        checked_blobs += 1
        try:
            if digest(path.read_bytes()) != path.stem:
                issue("blob_changed", path.name)
        except OSError:
            issue("blob_unreadable", path.name)
    return {"valid": not issues, "chain_valid": chain_valid, "head": head,
            "issues": issues, "warnings": warnings,
            "checked": {"documents": len(rows["documents"]), "decisions": len(rows["decisions"]),
                        "sources": len(rows["sources"]), "blobs": checked_blobs},
            "scope": "Eventos, manifiestos, originales, fuentes, decisiones y registros sellados; no identidad autenticada ni firma externa"}
