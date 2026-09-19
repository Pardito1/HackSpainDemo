from __future__ import annotations

import copy
import json
import os
import secrets
import statistics
import time
import threading
from functools import wraps
from datetime import date
from pathlib import Path

from .db import Store
from .erp import ERPClient
from .extract import FIELDS, VERSION, engine_versions, extract_pdf, invoice_number
from .master import read_master
from .policy import apply_reviews, evaluate, validate_policy
from .utils import canonical, clean, digest, identifier, invoice_date, money, now
from .workspace import WorkspaceMixin


def exclusive(function):
    """Single-host workflow lock. Nested calls reuse it; other writers fail clearly.

    SQLite transactions protect commits; this lock also protects multi-step previews,
    duplicate indexes and exports from concurrent CLI/UI changes. Reads stay available.
    """

    @wraps(function)
    def wrapped(self, *args, **kwargs):
        import fcntl

        if getattr(self._workflow, "held", False):
            return function(self, *args, **kwargs)
        with (self.store.root / "workflow.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(
                    "Hay un trabajo activo; espera a que termine antes de modificar o exportar"
                ) from exc
            self._workflow.held = True
            try:
                if not self.store.verify_audit()["valid"]:
                    raise ValueError("Operación bloqueada: la comprobación de integridad detecta alteraciones. Revisa Actividad y restaura la evidencia antes de continuar.")
                return function(self, *args, **kwargs)
            finally:
                self._workflow.held = False

    return wrapped


class Service(WorkspaceMixin):
    human_preview = exclusive(WorkspaceMixin.human_preview)
    human_commit = exclusive(WorkspaceMixin.human_commit)
    retract_human_answer = exclusive(WorkspaceMixin.retract_human_answer)
    preview_source = exclusive(WorkspaceMixin.preview_source)
    prepare_upload = exclusive(WorkspaceMixin.prepare_upload)
    prepare_erp = exclusive(WorkspaceMixin.prepare_erp)
    commit_source = exclusive(WorkspaceMixin.commit_source)

    def __init__(self, data_dir="data"):
        self.store = Store(data_dir)
        self._workflow = threading.local()
        self.code_sha256 = digest(
            {
                p.name: digest(p.read_bytes())
                for p in sorted(Path(__file__).parent.glob("*.py"))
            }
        )

    def batch(self, batch_id):
        batch = self.store.one("SELECT * FROM batches WHERE id=?", (batch_id,))
        if not batch:
            raise ValueError("Lote no encontrado")
        return batch

    def document(self, document_id):
        row = self.store.one("SELECT * FROM documents WHERE id=?", (document_id,))
        if not row:
            raise ValueError("Documento no encontrado")
        return row

    def policy(self, path=None, actor="equipo"):
        path = Path(path) if path else Path(__file__).parent / "policies" / "v3.json"
        policy = validate_policy(json.loads(path.read_text()))
        policy["approved_by"] = actor
        return self.store.put_source("policy", policy)

    @exclusive
    def ingest(self, folder, workbook, name, as_of, policy_path=None, actor="equipo"):
        date.fromisoformat(as_of)
        files = sorted(
            p
            for p in Path(folder).rglob("*")
            if p.is_file() and p.suffix.lower() == ".pdf"
        )
        if not files or len({p.name for p in files}) != len(files):
            raise ValueError("El lote debe contener PDFs y nombres de archivo únicos")
        workbook = Path(workbook)
        master = read_master(workbook)
        master["blob"] = str(self.store.blob(workbook.read_bytes(), ".xlsx"))
        master_id = self.store.put_source("master", master)
        policy_id = self.policy(policy_path, actor)
        batch_id = secrets.token_hex(6)
        manifest = []
        for file in files:
            data = file.read_bytes()
            if len(data) > 50 * 1024 * 1024 or not data.startswith(b"%PDF"):
                raise ValueError(f"PDF inválido o demasiado grande: {file.name}")
            blob = self.store.blob(data, ".pdf")
            manifest.append((secrets.token_hex(10), file.name, digest(data), str(blob)))
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Until the new batch is read we cannot exclude cross-batch duplicates.
            db.execute(
                "UPDATE documents SET latest_decision=NULL,state=CASE WHEN extraction IS NOT NULL THEN 'EXTRACTED' ELSE state END"
            )
            db.execute(
                "INSERT INTO batches VALUES(?,?,?,?,?,?,?)",
                (batch_id, name, master_id, policy_id, None, as_of, now()),
            )
            for doc_id, filename, sha, path in manifest:
                db.execute(
                    "INSERT INTO documents(id,batch_id,file_id,sha256,path,created) VALUES(?,?,?,?,?,?)",
                    (doc_id, batch_id, filename, sha, path, now()),
                )
                db.execute("INSERT INTO jobs(document_id) VALUES(?)", (doc_id,))
            self.store.event(
                "batch_ingested",
                {
                    "count": len(manifest),
                    "master_id": master_id,
                    "policy_id": policy_id,
                    "manifest": [{"file_id": m[1], "sha256": m[2]} for m in manifest],
                },
                batch_id=batch_id,
                db=db,
            )
        return {"batch_id": batch_id, "documents": len(manifest)}

    @exclusive
    def sync_erp(self, batch_id, url, user, password):
        old = self.batch(batch_id)
        # One sync globally: the supplied bridge has a global rate limit.
        lock = self.store.root / "erp-sync.lock"
        import fcntl

        with lock.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Ya hay una sincronización ERP activa") from exc
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE batches SET snapshot_id=NULL WHERE id=?", (batch_id,)
                )
                db.execute(
                    "UPDATE documents SET latest_decision=NULL,state=CASE WHEN extraction IS NULL THEN state ELSE 'WAITING_ERP' END WHERE batch_id=?",
                    (batch_id,),
                )
                self.store.event(
                    "erp_sync_started",
                    {"previous_snapshot": old["snapshot_id"]},
                    batch_id=batch_id,
                    db=db,
                )
            started = time.monotonic()
            client = ERPClient(
                url,
                user,
                password,
                callback=lambda kind, payload: self.store.event(
                    kind, payload, batch_id=batch_id
                ),
            )
            try:
                snapshot = client.snapshot()
                source_id = self.store.put_source("erp", snapshot)
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        "UPDATE batches SET snapshot_id=? WHERE id=?",
                        (source_id, batch_id),
                    )
                    self.store.cost(
                        "erp_sync",
                        time.monotonic() - started,
                        batch_id=batch_id,
                        payload={
                            "attempts": client.attempts,
                            "retries": client.retries,
                        },
                        db=db,
                    )
                    self.store.event(
                        "erp_snapshot_published",
                        {
                            "snapshot_id": source_id,
                            "total": snapshot["total"],
                            "pages": len(snapshot["pages"]),
                        },
                        batch_id=batch_id,
                        db=db,
                    )
                return {
                    "snapshot_id": source_id,
                    "total": snapshot["total"],
                    "attempts": client.attempts,
                    "retries": client.retries,
                }
            except Exception as exc:
                self.store.cost(
                    "erp_sync_failed",
                    time.monotonic() - started,
                    batch_id=batch_id,
                    payload={"error": str(exc)},
                )
                self.store.event(
                    "erp_sync_failed", {"error": str(exc)}, batch_id=batch_id
                )
                raise
            finally:
                client.close()

    def claim(self, batch_id):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute(
                """SELECT j.*,d.path,d.sha256,d.batch_id FROM jobs j JOIN documents d ON d.id=j.document_id
                WHERE d.batch_id=? AND ((j.state IN ('READY','RETRY_WAIT') AND j.next_at<=?) OR (j.state='RUNNING' AND j.lease_until<?))
                ORDER BY j.id LIMIT 1""",
                (batch_id, time.time(), time.time()),
            ).fetchone()
            if not job:
                return None
            token = secrets.token_hex(12)
            db.execute(
                "UPDATE jobs SET state='RUNNING',lease_until=?,lease_token=?,attempts=attempts+1 WHERE id=?",
                (time.time() + 600, token, job["id"]),
            )
            db.execute(
                "UPDATE documents SET state='EXTRACTING',latest_decision=NULL WHERE id=?",
                (job["document_id"],),
            )
            self.store.event(
                "extraction_claimed",
                {
                    "attempt": job["attempts"] + 1,
                    "recovered_lease": job["state"] == "RUNNING",
                },
                job["document_id"],
                batch_id,
                db,
            )
            return dict(job) | {"lease_token": token, "attempts": job["attempts"] + 1}

    @exclusive
    def process(self, batch_id, ocr=True, limit=None, fault_after=None):
        self.batch(batch_id)
        started = time.monotonic()
        count = 0
        while limit is None or count < limit:
            job = self.claim(batch_id)
            if not job:
                break
            key = digest(
                {
                    "sha256": job["sha256"],
                    "extractor": VERSION,
                    "engines": engine_versions(),
                    "ocr": ocr,
                }
            )
            cached = self.store.one(
                "SELECT payload FROM extraction_cache WHERE id=?", (key,)
            )
            step = time.monotonic()
            try:
                if digest(Path(job["path"]).read_bytes()) != job["sha256"]:
                    raise ValueError("El PDF almacenado ha sido alterado; restaura el original")
                extraction = (
                    json.loads(cached["payload"])
                    if cached
                    else extract_pdf(job["path"], ocr=ocr)
                )
                # Fault injection occurs after extraction, before the transaction. It leaves the lease recoverable.
                if fault_after is not None and count >= fault_after:
                    raise KeyboardInterrupt(
                        "Fallo de worker simulado después de extraer y antes de persistir"
                    )
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute(
                        "SELECT lease_token,state FROM jobs WHERE id=?", (job["id"],)
                    ).fetchone()
                    if (
                        current["lease_token"] != job["lease_token"]
                        or current["state"] != "RUNNING"
                    ):
                        continue  # fencing: an expired worker cannot overwrite its successor
                    db.execute(
                        "INSERT OR IGNORE INTO extraction_cache VALUES(?,?,?)",
                        (key, canonical(extraction), now()),
                    )
                    db.execute(
                        "UPDATE documents SET extraction=?,state='EXTRACTED' WHERE id=?",
                        (canonical(extraction), job["document_id"]),
                    )
                    db.execute(
                        "UPDATE jobs SET state='DONE',lease_until=0,error=NULL WHERE id=?",
                        (job["id"],),
                    )
                    self.store.cost(
                        "extract_cache" if cached else "extract",
                        time.monotonic() - step,
                        job["document_id"],
                        batch_id,
                        {
                            "cache_hit": bool(cached),
                            "pages": len(extraction["pages"]),
                            "engines": extraction["engines"],
                            "ocr_used": any(
                                p.get("method") == "rapidocr-onnxruntime"
                                for p in extraction["pages"]
                            ),
                        },
                        db=db,
                    )
                    self.store.event(
                        "extracted",
                        {
                            "cache_hit": bool(cached),
                            "version": VERSION,
                            "warnings": extraction["warnings"],
                        },
                        job["document_id"],
                        batch_id,
                        db,
                        records=[("extraction_cache", key)],
                    )
            except Exception as exc:
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute(
                        "SELECT lease_token FROM jobs WHERE id=?", (job["id"],)
                    ).fetchone()
                    if current[0] == job["lease_token"]:
                        state = "ERROR" if job["attempts"] >= 3 else "RETRY_WAIT"
                        db.execute(
                            "UPDATE jobs SET state=?,next_at=?,lease_until=0,error=? WHERE id=?",
                            (
                                state,
                                time.time() + 2 ** job["attempts"],
                                str(exc),
                                job["id"],
                            ),
                        )
                        db.execute(
                            "UPDATE documents SET state=? WHERE id=?",
                            (state, job["document_id"]),
                        )
                        self.store.event(
                            "extraction_failed",
                            {"error": str(exc), "state": state},
                            job["document_id"],
                            batch_id,
                            db,
                        )
                        self.store.cost(
                            "extract_failed",
                            time.monotonic() - step,
                            job["document_id"],
                            batch_id,
                            db=db,
                        )
            count += 1
        decided = self.reevaluate_all()[batch_id]
        self.store.event(
            "worker_run",
            {
                "processed": count,
                "wall_seconds": time.monotonic() - started,
                "ocr": ocr,
            },
            batch_id=batch_id,
        )
        return {"processed": count, **decided}

    def reviews(self, document_id):
        return [
            r | {"corrections": json.loads(r["corrections"])}
            for r in self.store.all(
                "SELECT * FROM reviews WHERE document_id=? ORDER BY id", (document_id,)
            )
        ]

    def effective(self, document):
        return (
            apply_reviews(
                json.loads(document["extraction"]), self.reviews(document["id"])
            )
            if document["extraction"]
            else None
        )

    def duplicate_context(self, document, extraction):
        related = []
        order = extraction["fields"]["order"]
        if order["status"] != "OK":
            return {"state": "none", "related": [], "canonical_id": None}
        for other in self.store.all(
            "SELECT * FROM documents WHERE extraction IS NOT NULL ORDER BY created,id"
        ):
            if other["id"] == document["id"]:
                continue
            effective = self.effective(other)
            other_order = effective["fields"]["order"]
            if other_order["status"] == "OK" and other_order["value"] == order["value"]:
                related.append(
                    {
                        "id": other["id"],
                        "file_id": other["file_id"],
                        "sha256": other["sha256"],
                        "batch_id": other["batch_id"],
                        "created": other["created"],
                    }
                )
        if not related:
            return {"state": "none", "related": [], "canonical_id": document["id"]}
        same = all(r["sha256"] == document["sha256"] for r in related)
        canonical_doc = min(
            [{"id": document["id"], "created": document["created"]}] + related,
            key=lambda r: (r["created"], r["id"]),
        )["id"]
        return {
            "state": (
                ("none" if canonical_doc == document["id"] else "confirmed_copy")
                if same
                else "conflict"
            ),
            "canonical_id": canonical_doc if same else None,
            "related": sorted([{k: v for k, v in r.items() if k != "created"} for r in related], key=lambda r: r["id"]),
        }

    def evaluation(self, document, extraction=None, duplicate=None, overrides=None, with_human=True):
        batch = self.batch(document["batch_id"])
        if overrides:
            batch = batch | overrides
        if not batch["snapshot_id"]:
            return None
        extraction = extraction or self.effective(document)
        if extraction is None:
            return None
        master = self.store.source(batch["master_id"])
        snapshot = self.store.source(batch["snapshot_id"])
        policy = self.store.source(batch["policy_id"])
        dup = (
            duplicate
            if duplicate is not None
            else self.duplicate_context(document, extraction)
        )
        result = evaluate(extraction, master, snapshot, policy, batch["as_of"], dup)
        result["context"] = {
            "master_id": batch["master_id"],
            "snapshot_id": batch["snapshot_id"],
            "policy_id": batch["policy_id"],
            "document_sha256": document["sha256"],
            "extraction_version": extraction["version"],
            "as_of": batch["as_of"],
            "code_sha256": self.code_sha256,
        }
        # A human response belongs to the facts reviewed, not merely to a filename.
        result["human_anchor"] = digest({
             "reviews": self.reviews(document["id"]),
             "result": {k: v for k, v in result.items() if k != "context"},
             "policy_id": batch["policy_id"], "document_sha256": document["sha256"],
             "code_sha256": self.code_sha256})
        result["engine_result"] = result["result"]
        if with_human:
            answer = self.store.one(
                "SELECT * FROM human_decisions WHERE document_id=? AND retracted_at IS NULL ORDER BY id DESC LIMIT 1",
                (document["id"],),
            )
            if answer and answer["anchor"] == result["human_anchor"]:
                result["human_decision"] = answer
                result["result"] = answer["result"]
                result["reason"] = "Respuesta de " + answer["actor"] + ": " + answer["reason"]
                result["questions"] = (["Consulta abierta: " + answer["reason"]]
                                       if answer["result"] == "ESCALAR" else [])
            elif answer:
                result["human_response_stale"] = True
                result["result"] = "ESCALAR"
                result["reason"] = "Ha cambiado la evidencia de una respuesta humana; Alberto debe revisarla de nuevo"
                result["questions"] = ["Revalida tu respuesta anterior con las fuentes actuales."] + result["questions"]
        result["context_hash"] = digest(result)
        return result

    @exclusive
    def evaluate_batch(self, batch_id, document_ids=None):
        batch = self.batch(batch_id)
        pending = self.store.one("SELECT count(*) n FROM jobs WHERE state!='DONE'")["n"]
        if pending:
            return {"decisions": 0, "pending_jobs": pending}
        if not batch["snapshot_id"]:
            with self.store.connect() as db:
                db.execute(
                    "UPDATE documents SET state='WAITING_ERP' WHERE batch_id=?",
                    (batch_id,),
                )
            return {"decisions": 0, "waiting_erp": True}
        docs = self.store.all(
            "SELECT * FROM documents WHERE batch_id=? ORDER BY file_id", (batch_id,)
        )
        if document_ids is not None:
            docs = [d for d in docs if d["id"] in set(document_ids)]
        # Build the obligation index once, including other batches. Avoid an N² database scan.
        by_order = {}
        all_docs = self.store.all(
            "SELECT * FROM documents WHERE extraction IS NOT NULL"
        )
        effective = {d["id"]: self.effective(d) for d in all_docs}
        for d in all_docs:
            field = effective[d["id"]]["fields"]["order"]
            if field["status"] == "OK":
                by_order.setdefault(field["value"], []).append(d)
        for document in docs:
            decision_start = time.monotonic()
            extraction = effective[document["id"]]
            field = extraction["fields"]["order"]
            group = by_order.get(field["value"], []) if field["status"] == "OK" else []
            related = [
                {
                    "id": d["id"],
                    "file_id": d["file_id"],
                    "batch_id": d["batch_id"],
                    "sha256": d["sha256"],
                }
                for d in group
                if d["id"] != document["id"]
            ]
            same = len({d["sha256"] for d in group}) == 1
            canonical_doc = (
                min(group, key=lambda d: (d["created"], d["id"]))["id"]
                if group
                else None
            )
            duplicate = {
                "state": (
                    "none"
                    if not related or same and canonical_doc == document["id"]
                    else "confirmed_copy" if same else "conflict"
                ),
                "canonical_id": canonical_doc if same else None,
                "related": sorted(related, key=lambda r: r["id"]),
            }
            result = self.evaluation(document, extraction, duplicate)
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                # Prevent publishing a decision computed against a replaced source.
                current = db.execute(
                    "SELECT snapshot_id,policy_id,master_id,as_of FROM batches WHERE id=?",
                    (batch_id,),
                ).fetchone()
                if any(current[k] != result["context"][k] for k in current.keys()):
                    raise ValueError(
                        "Las fuentes cambiaron durante la evaluación; repetir"
                    )
                db.execute(
                    "INSERT OR IGNORE INTO decisions(document_id,context_hash,result,payload,created) VALUES(?,?,?,?,?)",
                    (
                        document["id"],
                        result["context_hash"],
                        result["result"],
                        canonical(result),
                        now(),
                    ),
                )
                decision_id = db.execute(
                    "SELECT id FROM decisions WHERE document_id=? AND context_hash=?",
                    (document["id"], result["context_hash"]),
                ).fetchone()[0]
                db.execute(
                    "UPDATE documents SET latest_decision=?,state=? WHERE id=?",
                    (
                        decision_id,
                        "HUMAN_REVIEW" if result["result"] == "ESCALAR" else "DECIDED",
                        document["id"],
                    ),
                )
                if decision_id != document["latest_decision"]:
                    self.store.event(
                        "decision_published",
                        {
                            "decision_id": decision_id,
                            "result": result["result"],
                            "context_hash": result["context_hash"],
                        },
                        document["id"],
                        batch_id,
                        db,
                    )
                self.store.cost(
                    "evaluate",
                    time.monotonic() - decision_start,
                    document["id"],
                    batch_id,
                    db=db,
                )
        return {"decisions": len(docs), "pending_jobs": 0}

    @exclusive
    def reevaluate_all(self):
        return {
            b["id"]: self.evaluate_batch(b["id"])
            for b in self.store.all("SELECT * FROM batches ORDER BY created")
        }

    def correction(self, field, value):
        if field not in (*FIELDS, "currency"):
            raise ValueError("Campo no corregible")
        if field in ("base", "tax_rate", "tax_amount", "total"):
            return str(money(value))
        if field == "date":
            return invoice_date(value)
        if field == "invoice_number":
            return invoice_number(value)
        s = identifier(value)
        if not s or len(s) > 120:
            raise ValueError("Valor vacío o demasiado largo")
        return s

    @exclusive
    def preview_review(self, document_ids, field, value, actor, reason):
        if not clean(actor) or len(clean(reason)) < 10:
            raise ValueError(
                "Indica autor y una justificación de al menos 10 caracteres"
            )
        value = self.correction(field, value)
        ids = sorted(set(document_ids))
        if not ids or len(ids) > 500:
            raise ValueError("Selecciona entre 1 y 500 documentos")
        previews = []
        all_effective = {}
        selected = {}
        for doc in self.store.all(
            "SELECT * FROM documents WHERE extraction IS NOT NULL"
        ):
            effective = self.effective(doc)
            if doc["id"] in ids:
                effective["fields"][field] = {
                    "value": value,
                    "status": "OK",
                    "evidence": [
                        {"method": "human_preview", "actor": actor, "reason": reason}
                    ],
                }
                selected[doc["id"]] = doc
            all_effective[doc["id"]] = (doc, effective)
        if len(selected) != len(ids):
            raise ValueError("Todos los documentos deben existir y estar extraídos")
        dependencies = []
        for doc, effective in all_effective.values():
            dependencies.append(
                (
                    doc["id"],
                    doc["sha256"],
                    digest(doc["extraction"]),
                    self.reviews(doc["id"]),
                )
            )
        for doc_id in ids:
            doc, effective = all_effective[doc_id]
            order = effective["fields"]["order"]
            group = [
                d
                for d, e in all_effective.values()
                if order["status"] == "OK"
                and e["fields"]["order"]["status"] == "OK"
                and e["fields"]["order"]["value"] == order["value"]
            ]
            canonical_doc = (
                min(group, key=lambda d: (d["created"], d["id"]))["id"]
                if group
                else None
            )
            same = len({d["sha256"] for d in group}) == 1
            related = [
                {"id": d["id"], "file_id": d["file_id"]}
                for d in group
                if d["id"] != doc_id
            ]
            dup = {
                "state": (
                    "none"
                    if not related or same and canonical_doc == doc_id
                    else "confirmed_copy" if same else "conflict"
                ),
                "related": related,
                "canonical_id": canonical_doc if same else None,
            }
            after = self.evaluation(doc, effective, dup)
            before = self.store.one(
                "SELECT result FROM decisions WHERE id=?", (doc["latest_decision"],)
            )
            previews.append(
                {
                    "id": doc_id,
                    "file_id": doc["file_id"],
                    "before": before["result"] if before else None,
                    "after": after["result"] if after else None,
                    "remaining_questions": (
                        after["questions"] if after else ["Falta snapshot ERP"]
                    ),
                }
            )
        payload = {
            "ids": ids,
            "field": field,
            "value": value,
            "actor": clean(actor),
            "reason": clean(reason),
            "previews": previews,
        }
        payload["preview_token"] = digest(
            {
                "payload": payload,
                "dependencies": dependencies,
                "batches": self.store.all("SELECT * FROM batches ORDER BY id"),
            }
        )
        return payload

    @exclusive
    def commit_review(self, document_ids, field, value, actor, reason, preview_token):
        preview = self.preview_review(document_ids, field, value, actor, reason)
        if preview_token != preview["preview_token"]:
            raise ValueError(
                "La evidencia cambió desde la simulación. Vuelve a previsualizar"
            )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for doc_id in preview["ids"]:
                db.execute(
                    "INSERT INTO reviews(document_id,actor,reason,corrections,created) VALUES(?,?,?,?,?)",
                    (
                        doc_id,
                        preview["actor"],
                        preview["reason"],
                        canonical({field: preview["value"]}),
                        now(),
                    ),
                )
                db.execute(
                    "UPDATE documents SET latest_decision=NULL,state='EXTRACTED' WHERE id=?",
                    (doc_id,),
                )
                self.store.event(
                    "human_correction",
                    {
                        "field": field,
                        "value": preview["value"],
                        "actor": preview["actor"],
                        "reason": preview["reason"],
                        "scope": preview["ids"],
                    },
                    doc_id,
                    db=db,
                )
        self.reevaluate_all()
        return preview

    @exclusive
    def change_policy(self, batch_id, path, actor):
        self.batch(batch_id)
        policy_id = self.policy(path, actor)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE batches SET policy_id=? WHERE id=?", (policy_id, batch_id)
            )
            db.execute(
                "UPDATE documents SET latest_decision=NULL WHERE batch_id=?",
                (batch_id,),
            )
            self.store.event(
                "policy_changed",
                {"policy_id": policy_id, "actor": actor},
                batch_id=batch_id,
                db=db,
            )
        return self.evaluate_batch(batch_id)

    @exclusive
    def retry(self, batch_id, expired_only=True):
        self.batch(batch_id)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Never steal a live lease; restart recovery is automatic after 10 min.
            changed = db.execute(
                "UPDATE jobs SET state='READY',next_at=0,error=NULL WHERE document_id IN (SELECT id FROM documents WHERE batch_id=?) AND (state IN ('RETRY_WAIT','ERROR') OR (state='RUNNING' AND lease_until<?))",
                (batch_id, time.time()),
            ).rowcount
            self.store.event(
                "jobs_requeued", {"count": changed}, batch_id=batch_id, db=db
            )
        return {"requeued": changed}

    @exclusive
    def reextract(self, batch_id):
        """Explicitly create new extractions without erasing history or cached evidence."""
        self.batch(batch_id)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE documents SET latest_decision=NULL")
            db.execute(
                "UPDATE documents SET extraction=NULL,state='QUEUED' WHERE batch_id=?",
                (batch_id,),
            )
            changed = db.execute(
                "UPDATE jobs SET state='READY',next_at=0,lease_until=0,lease_token=NULL,error=NULL WHERE document_id IN (SELECT id FROM documents WHERE batch_id=?)",
                (batch_id,),
            ).rowcount
            self.store.event(
                "reextraction_requested",
                {"count": changed, "extractor_version": VERSION},
                batch_id=batch_id,
                db=db,
            )
        return {"requeued": changed}

    @exclusive
    def export_rows(self, batch_id):
        self.batch(batch_id)
        audit = self.store.verify_audit()
        if not audit["valid"]:
            raise ValueError("Exportación bloqueada: la comprobación de integridad ha detectado alteraciones. Revisa Actividad.")
        rows = self.store.all(
            "SELECT d.file_id,d.latest_decision,x.result,x.payload FROM documents d LEFT JOIN decisions x ON x.id=d.latest_decision WHERE d.batch_id=? ORDER BY d.file_id",
            (batch_id,),
        )
        missing = [r["file_id"] for r in rows if not r["result"]]
        if missing:
            raise ValueError(
                f"Exportación bloqueada: {len(missing)} documentos sin decisión final"
            )
        if not rows or len({r["file_id"] for r in rows}) != len(rows):
            raise ValueError("Manifiesto vacío o duplicado")
        if any(json.loads(r["payload"])["context"].get("code_sha256") != self.code_sha256 for r in rows):
            raise ValueError("Exportación bloqueada: el código ha cambiado; reprocesa las lecturas y reevalúa el lote")
        return [{"file_id": r["file_id"], "result": r["result"]} for r in rows]

    def export(self, batch_id, path):
        rows = self.export_rows(batch_id)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
        try:
            tmp.write_text("".join(canonical(r) + "\n" for r in rows), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        self.store.event(
            "exported",
            {"count": len(rows), "sha256": digest(path.read_bytes())},
            batch_id=batch_id,
        )
        return {"file": str(path), "count": len(rows)}

    def dashboard(self, batch_id=None):
        where = "WHERE d.batch_id=?" if batch_id else ""
        params = (batch_id,) if batch_id else ()
        docs = self.store.all(
            f"SELECT d.*,x.result,x.payload FROM documents d LEFT JOIN decisions x ON x.id=d.latest_decision {where} ORDER BY d.created,d.file_id",
            params,
        )
        items = []
        for d in docs:
            decision = json.loads(d.pop("payload")) if d["payload"] else None
            extraction = json.loads(d.pop("extraction")) if d["extraction"] else None
            fields = (
                decision["fields"]
                if decision
                else extraction["fields"] if extraction else {}
            )
            items.append(
                d
                | {
                    "total": fields.get("total", {}).get("value"),
                    "nif": fields.get("supplier_nif", {}).get("value"),
                    "reason": decision["reason"] if decision else d["state"],
                    "questions": decision["questions"] if decision else [],
                    "order": fields.get("order", {}).get("value"),
                    "currency": fields.get("currency", {}).get("value"),
                    "invoice_number": fields.get("invoice_number", {}).get("value"),
                    "human": bool(decision and decision.get("human_decision")),
                    "human_stale": bool(decision and decision.get("human_response_stale")),
                }
            )
        counts = {
            state: sum(d["result"] == state for d in items)
            for state in ("PAGAR", "NO_PAGAR", "ESCALAR")
        }
        costs = self.store.all(
            "SELECT * FROM costs" + (" WHERE batch_id=?" if batch_id else ""), params
        )

        def percentiles(times):
            times = sorted(times)
            if not times:
                return None, None
            p50 = statistics.median(times)
            p95 = times[min(len(times) - 1, int(len(times) * 0.95))]
            return p50, p95

        extraction_costs = [c for c in costs if c["stage"] in ("extract", "extract_cache")]
        ocr_times, text_times = [], []
        for c in extraction_costs:
            payload = json.loads(c["payload"]) if c["payload"] else {}
            (ocr_times if payload.get("ocr_used") else text_times).append(c["seconds"])
        extract_p50, extract_p95 = percentiles([c["seconds"] for c in extraction_costs])
        ocr_p50, ocr_p95 = percentiles(ocr_times)
        text_p50, text_p95 = percentiles(text_times)
        wall_events = self.store.all(
            "SELECT payload FROM events WHERE kind='worker_run'"
            + (" AND batch_id=?" if batch_id else ""),
            params,
        )
        run_records = []
        for e in wall_events:
            run = json.loads(e["payload"])
            run["per_second"] = run["processed"] / run["wall_seconds"] if run["wall_seconds"] else None
            run_records.append(run)
        metrics = {
            "documents": len(items),
            "decisions": sum(counts.values()),
            "pending": len(items) - sum(counts.values()),
            "counts": counts,
            "external_eur": sum(c["external_eur"] for c in costs),
            "compute_seconds": sum(c["seconds"] for c in costs if c["stage"] != "human_review"),
            "human_seconds": sum(c["seconds"] for c in costs if c["stage"] == "human_review"),
            "human_responses": sum(c["stage"] == "human_review" for c in costs),
            "extract_p50": extract_p50,
            "extract_p95": extract_p95,
            "extract_ocr_p50": ocr_p50,
            "extract_ocr_p95": ocr_p95,
            "extract_ocr_count": len(ocr_times),
            "extract_text_p50": text_p50,
            "extract_text_p95": text_p95,
            "extract_text_count": len(text_times),
            "worker_runs": run_records,
            "cost_note": "Sin llamadas de pago. Infraestructura y tiempo humano no valorados; no equivalen a coste cero.",
            "accuracy": None,
            "accuracy_note": "Pendiente de etiquetas humanas independientes.",
        }
        return {
            "documents": items,
            "metrics": metrics,
            "batches": self.store.all("SELECT * FROM batches ORDER BY created DESC"),
        }

    def detail(self, doc_id):
        doc = self.document(doc_id)
        extraction = json.loads(doc["extraction"]) if doc["extraction"] else None
        history = self.store.all(
            "SELECT * FROM decisions WHERE document_id=? ORDER BY id DESC", (doc_id,)
        )
        current = self.store.one(
            "SELECT * FROM decisions WHERE id=?", (doc["latest_decision"],)
        )
        return {
            "document": doc,
            "batch": self.batch(doc["batch_id"]),
            "extraction": extraction,
            "decision": json.loads(current["payload"]) if current else None,
            "history": history,
            "reviews": self.reviews(doc_id),
            "human_answers": self.store.all("SELECT * FROM human_decisions WHERE document_id=? ORDER BY id DESC", (doc_id,)),
            "events": [
                r | {"payload": json.loads(r["payload"])}
                for r in self.store.all(
                    "SELECT * FROM events WHERE document_id=? ORDER BY id DESC",
                    (doc_id,),
                )
            ],
            "costs": self.store.all(
                "SELECT * FROM costs WHERE document_id=?", (doc_id,)
            ),
        }

    def groups(self, batch_id=None):
        dashboard = self.dashboard(batch_id)
        groups = {}
        for d in dashboard["documents"]:
            if d["result"] != "ESCALAR":
                continue
            detail = self.detail(d["id"])
            for rule in detail["decision"]["rules"]:
                if rule["state"] == "PASS" or rule["id"].startswith("field:"):
                    continue
                # A shared cause requires the same identity and the same actual evidence, not just the same label.
                batch = detail["batch"]
                key = digest(
                    {
                        "rule": rule["id"],
                        "nif": d["nif"],
                        "evidence": rule["evidence"],
                        "master": batch["master_id"],
                        "snapshot": batch["snapshot_id"],
                        "policy": batch["policy_id"],
                    }
                )
                group = groups.setdefault(
                    key,
                    {
                        "id": key,
                        "rule": rule["id"],
                        "nif": d["nif"],
                        "question": rule["question"],
                        "documents": [],
                    },
                )
                group["documents"].append({"id": d["id"], "file_id": d["file_id"]})
        return sorted(groups.values(), key=lambda g: -len(g["documents"]))
