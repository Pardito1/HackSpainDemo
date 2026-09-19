from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .utils import canonical, digest, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, name TEXT NOT NULL, master_id TEXT NOT NULL REFERENCES sources(id),
 policy_id TEXT NOT NULL REFERENCES sources(id), snapshot_id TEXT REFERENCES sources(id), as_of TEXT NOT NULL,
 extraction_profile TEXT NOT NULL DEFAULT 'standard', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
 file_id TEXT NOT NULL, sha256 TEXT NOT NULL, path TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'RECEIVED',
 extraction TEXT, latest_decision INTEGER, created TEXT NOT NULL, UNIQUE(batch_id,file_id));
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
 state TEXT NOT NULL DEFAULT 'READY', lease_until REAL NOT NULL DEFAULT 0, lease_token TEXT,
 attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS extraction_cache(id TEXT PRIMARY KEY, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 context_hash TEXT NOT NULL, result TEXT NOT NULL CHECK(result IN ('PAGAR','NO_PAGAR','ESCALAR')),
 payload TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(document_id,context_hash));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 actor TEXT NOT NULL, reason TEXT NOT NULL, corrections TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS human_decisions(id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 anchor TEXT NOT NULL, result TEXT NOT NULL CHECK(result IN ('PAGAR','NO_PAGAR','ESCALAR')), actor TEXT NOT NULL,
 reason TEXT NOT NULL, evidence TEXT NOT NULL, acknowledged TEXT NOT NULL, seconds REAL NOT NULL, created TEXT NOT NULL,
 retracted_at TEXT, retracted_by TEXT, retracted_reason TEXT);
CREATE TABLE IF NOT EXISTS source_changes(id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
 kind TEXT NOT NULL, old_id TEXT NOT NULL, new_id TEXT NOT NULL REFERENCES sources(id), payload TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'PREVIEW', created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS human_document ON human_decisions(document_id);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, document_id TEXT, batch_id TEXT,
 kind TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS costs(id INTEGER PRIMARY KEY, document_id TEXT, batch_id TEXT, stage TEXT NOT NULL,
 seconds REAL NOT NULL, external_eur REAL NOT NULL DEFAULT 0, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS docs_batch ON documents(batch_id);
CREATE INDEX IF NOT EXISTS events_doc ON events(document_id);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Audit events are append-only'); END;
"""


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "blobs").mkdir(exist_ok=True)
        current = self.root / "factu.sqlite3"
        legacy = self.root / "alberto.sqlite3"
        if current.exists() and legacy.exists():
            raise ValueError("Hay dos bases de datos en esta carpeta. Conserva una copia y elige una carpeta con una sola base antes de continuar.")
        # Reuse previous installations without silently opening an empty desk.
        self.path = legacy if legacy.exists() else current
        with self.connect() as db:
            db.executescript(SCHEMA)
            # Additive migrations: CREATE TABLE IF NOT EXISTS does not add
            # columns to an existing local desk.  A profile belongs to the
            # batch, rather than to the global installation, so an initial
            # batch and Lote 2 can be replayed together without changing each
            # other's extraction path.
            existing = {r[1] for r in db.execute("PRAGMA table_info(human_decisions)")}
            for column in ("retracted_at", "retracted_by", "retracted_reason"):
                if column not in existing:
                    db.execute(f"ALTER TABLE human_decisions ADD COLUMN {column} TEXT")
            batch_columns = {r[1] for r in db.execute("PRAGMA table_info(batches)")}
            if "extraction_profile" not in batch_columns:
                db.execute(
                    "ALTER TABLE batches ADD COLUMN extraction_profile TEXT NOT NULL DEFAULT 'standard'"
                )
        token_path = self.root / ".csrf-token"
        try:
            with token_path.open("x") as handle:
                handle.write(secrets.token_urlsafe(32))
            token_path.chmod(0o600)
        except FileExistsError:
            pass
        self.csrf_token = token_path.read_text()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def all(self, sql, params=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, params)]

    def one(self, sql, params=()):
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def source(self, source_id):
        row = self.one("SELECT * FROM sources WHERE id=?", (source_id,))
        if not row:
            raise ValueError("Fuente no encontrada")
        return json.loads(row["payload"])

    def put_source(self, kind, payload):
        source_id = digest({"kind": kind, "payload": payload})
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO sources VALUES(?,?,?,?)",
                (source_id, kind, canonical(payload), now()),
            )
            self.event("source_registered", {}, db=db, records=[("sources", source_id)])
        return source_id

    def blob(self, data: bytes, suffix: str) -> Path:
        path = self.root / "blobs" / (digest(data) + suffix)
        if not path.exists():
            with path.open("xb") as handle:
                handle.write(data)
        elif digest(path.read_bytes()) != digest(data):
            raise ValueError("Original almacenado alterado: restaura la copia antes de continuar")
        return path

    def event(self, kind, payload, document_id=None, batch_id=None, db=None, records=None):
        if db is None:
            with self.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                return self.event(kind, payload, document_id, batch_id, connection, records)
        payload = dict(payload)
        records = list(records or [])
        if kind == "decision_published":
            records.append(("decisions", payload["decision_id"]))
        if kind in ("human_correction", "alberto_answered"):
            table = "reviews" if kind == "human_correction" else "human_decisions"
            record = db.execute(f"SELECT id FROM {table} WHERE document_id=? ORDER BY id DESC LIMIT 1", (document_id,)).fetchone()
            records.append((table, record[0]))
        if kind == "extracted":
            extraction = db.execute("SELECT extraction FROM documents WHERE id=?", (document_id,)).fetchone()[0]
            payload["extraction_sha256"] = digest(json.loads(extraction))
        if kind == "batch_ingested":
            records.extend(("documents", r[0]) for r in db.execute("SELECT id FROM documents WHERE batch_id=?", (batch_id,)))
        if records:
            payload["_records"] = []
            for table, record_id in records:
                if table not in ("sources", "decisions", "reviews", "human_decisions", "documents", "extraction_cache"):
                    raise ValueError("Tabla no sellable")
                row = dict(db.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone())
                if table == "documents":
                    row = {k: row[k] for k in ("id", "batch_id", "file_id", "sha256", "path", "created")}
                payload["_records"].append({"table": table, "id": record_id, "columns": sorted(row), "sha256": digest(row)})
        row = db.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev = row[0] if row else "0" * 64
        stamp = now()
        body = {
            "kind": kind,
            "payload": payload,
            "document_id": document_id,
            "batch_id": batch_id,
            "created": stamp,
            "prev_hash": prev,
        }
        db.execute(
            "INSERT INTO events(document_id,batch_id,kind,payload,created,prev_hash,hash) VALUES(?,?,?,?,?,?,?)",
            (
                document_id,
                batch_id,
                kind,
                canonical(payload),
                stamp,
                prev,
                digest(body),
            ),
        )

    def cost(
        self,
        stage,
        seconds,
        document_id=None,
        batch_id=None,
        payload=None,
        external_eur=0,
        db=None,
    ):
        if db is None:
            with self.connect() as connection:
                return self.cost(
                    stage,
                    seconds,
                    document_id,
                    batch_id,
                    payload,
                    external_eur,
                    connection,
                )
        db.execute(
            "INSERT INTO costs(document_id,batch_id,stage,seconds,external_eur,payload,created) VALUES(?,?,?,?,?,?,?)",
            (
                document_id,
                batch_id,
                stage,
                seconds,
                external_eur,
                canonical(payload or {}),
                now(),
            ),
        )

    def verify_audit(self):
        from .integrity import verify
        return verify(self)
