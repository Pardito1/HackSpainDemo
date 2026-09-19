"""Checklist PDF, through real loopback HTTP; never touches the official ERP.

FACTU_QA_OUTPUT saves checkpoints, SQL evidence, complete trace and outcomes.
The state is a pytest temporary directory populated only with synthetic fixtures.
"""
import json
import os
import socket
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import httpx
from factu.erp import ERPClient, ERPUnavailable
from factu.service import Service
from factu.utils import digest, now
from fastapi.testclient import TestClient
from factu.web import create_app
from test_erp_web import XML


@pytest.fixture
def provider(monkeypatch):
    state = {"mode": "ok", "entered": threading.Event()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.reply(200, b"<erp><token>qa-token</token></erp>")
        def reply(self, status, body, headers=None):
            self.send_response(status)
            for key, value in (headers or {}).items(): self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
        def do_GET(self):
            state["entered"].set()
            mode = state["mode"]
            if mode == "timeout":
                time.sleep(.3)  # exceeds real 80 ms client timeout
            if mode in ("http500", "rate_limit"):
                return self.reply(500 if mode=="http500" else 429, b"provider unavailable", {"Retry-After":"0"})
            if mode == "malformed": return self.reply(200, b"<erp><not-closed")
            if mode == "partial":
                if "pagina=2" in self.path: return self.reply(500, b"page unavailable")
                return self.reply(200, XML.replace("<total>1", "<total>2").replace("<paginas>1", "<paginas>2").encode())
            self.reply(200, XML.encode("iso-8859-1"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    class BoundedClient(ERPClient):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw, timeout=.08, max_attempts=3, interval=0)
    monkeypatch.setattr("factu.service.ERPClient", BoundedClient)
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def checkpoint(s, batch, label):
    return {"at": now(), "label": label,
            "rows": s.store.all("SELECT d.file_id,d.state,d.latest_decision,j.state job_state,j.attempts FROM documents d JOIN jobs j ON j.document_id=d.id WHERE d.batch_id=?", (batch,))}


@pytest.mark.parametrize("failure", ["timeout", "malformed", "http500", "rate_limit", "offline", "partial"])
def test_all_provider_failure_steps(bundle, provider, failure, tmp_path):
    s, batch, folder, workbook = bundle
    state, healthy_url = provider
    # No previous snapshot: extraction is useful and durable even while ERP is down.
    with s.store.connect() as db:
        db.execute("UPDATE batches SET snapshot_id=NULL WHERE id=?", (batch,))
    s.process(batch, ocr=False)
    doc = s.store.one("SELECT * FROM documents")
    original_sha, extraction = doc["sha256"], doc["extraction"]
    checkpoints = [checkpoint(s, batch, "Lectura conservada; esperando contabilidad")]
    assert doc["state"] == "WAITING_ERP" and doc["extraction"]
    state["mode"] = failure
    closed = socket.socket()
    closed.bind(("127.0.0.1",0))  # bound but not listening: reliably refused locally
    failed_url = f"http://127.0.0.1:{closed.getsockname()[1]}" if failure=="offline" else healthy_url
    try:
        with pytest.raises(ERPUnavailable):
            s.sync_erp(batch, failed_url, "qa-user", "qa-password")
    finally:
        closed.close()
    checkpoints.append(checkpoint(s, batch, "Fallo capturado y estado guardado"))
    frozen = s.document(doc["id"])
    assert frozen["state"] == "ERP_ERROR" and frozen["extraction"] == extraction
    assert digest(Path(frozen["path"]).read_bytes()) == original_sha
    assert s.batch(batch)["snapshot_id"] is None  # never publish partial pages
    failure_event = s.store.one("SELECT * FROM events WHERE kind='erp_sync_failed' ORDER BY id DESC LIMIT 1")
    assert failure_event["created"] and json.loads(failure_event["payload"])["error"]
    s.process(batch, ocr=False)  # a retry cannot erase the error or re-extract twice
    assert s.document(doc["id"])["state"] == "ERP_ERROR"
    out = tmp_path / "outcomes.jsonl"
    with pytest.raises(ValueError): s.export(batch, out)
    assert not out.exists()
    with TestClient(create_app(s.store.root)) as client:
        page = client.get("/documents/"+doc["id"])
        assert page.status_code == 200 and "CONSULTA INTERRUMPIDA" in page.text
    # Manual operator retry. Restarting the service proves persistence, not RAM recovery.
    state["mode"] = "ok"
    s = Service(s.store.root)
    s.sync_erp(batch, healthy_url, "qa-user", "qa-password")
    s.process(batch, ocr=False)
    checkpoints.append(checkpoint(s, batch, "ERP recuperado; comprobaciones terminadas"))
    assert s.document(doc["id"])["state"] == "DECIDED"
    assert s.document(doc["id"])["extraction"] == extraction
    assert s.store.one("SELECT attempts FROM jobs")["attempts"] == 1
    s.export(batch, out)
    counts = Counter(json.loads(line)["file_id"] for line in out.read_text().splitlines())
    assert list(counts.values()) == [1]
    decisions = s.store.one("SELECT count(*) n FROM decisions")["n"]
    s.process(batch, ocr=False)
    s.export(batch, out)
    assert s.store.one("SELECT count(*) n FROM decisions")["n"] == decisions
    assert len(out.read_text().splitlines()) == 1
    assert s.store.all("SELECT batch_id,file_id,count(*) n FROM documents GROUP BY batch_id,file_id HAVING count(*)>1") == []
    # Repeated document in another batch still needs one output per input, but
    # cannot yield a second payable obligation.
    second = s.ingest(folder, workbook, "QA second batch", "2026-09-19")["batch_id"]
    s.sync_erp(second, healthy_url, "qa-user", "qa-password")
    s.process(second, ocr=False)
    assert s.export_rows(batch)[0]["result"] == "PAGAR"
    assert s.export_rows(second)[0]["result"] == "NO_PAGAR"
    assert s.store.verify_audit()["valid"]
    events = s.store.all("SELECT * FROM events ORDER BY id")
    report = {"case": failure, "passed": True, "transport": "real localhost HTTP",
        "timeout_seconds": .08, "max_attempts": 3, "production_max_attempts": 5,
        "recovery": "manual resync and reevaluate; preserved OCR",
        "original_unchanged": True, "extraction_unchanged": True,
        "no_output_during_failure": True, "unique_output": dict(counts),
        "cross_batch_results": [s.export_rows(batch), s.export_rows(second)],
        "checkpoints": checkpoints, "error_event": failure_event,
        "sql_duplicate_query": "SELECT batch_id,file_id,count(*) FROM documents GROUP BY batch_id,file_id HAVING count(*)>1",
        "sql_duplicate_rows": [], "audit": s.store.verify_audit()}
    if os.getenv("FACTU_QA_OUTPUT"):
        target = Path(os.environ["FACTU_QA_OUTPUT"]) / failure
        target.mkdir(parents=True, exist_ok=True)
        (target / "verificacion.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (target / "trazabilidad.jsonl").write_text("".join(json.dumps(e,ensure_ascii=False)+"\n" for e in events))
        (target / "outcomes.jsonl").write_bytes(out.read_bytes())


def test_concurrent_retry_is_blocked(bundle, provider):
    s, batch, *_ = bundle
    state, url = provider
    s.process(batch, ocr=False)
    state["mode"] = "timeout"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(s.sync_erp, batch, url, "qa", "qa")
        assert state["entered"].wait(2)
        with pytest.raises(ValueError, match="trabajo activo"):
            Service(s.store.root).process(batch, ocr=False)
        with pytest.raises(ERPUnavailable): future.result(timeout=5)


@pytest.mark.parametrize("header", ["not-a-date", "Infinity", "NaN"])
def test_bad_retry_after_uses_bounded_backoff(monkeypatch, header):
    monkeypatch.setattr("factu.erp.time.sleep", lambda _: None)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After":header}) if len(calls)==1 else httpx.Response(200,content=XML.encode())
    client = ERPClient("http://erp.test", "qa", "qa", interval=0)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(respond))
    client.token = "qa"
    try:
        assert client.snapshot()["total"] == 1 and len(calls)==2
    finally: client.close()
