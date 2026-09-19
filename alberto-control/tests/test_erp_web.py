import json
import httpx
import pytest
from fastapi.testclient import TestClient
from alberto.erp import ERPClient, ERPUnavailable
from alberto.web import create_app

XML = """<?xml version="1.0" encoding="ISO-8859-1"?><erp><meta><total>1</total><paginas>1</paginas></meta><asientos><asiento><id>1</id><fecha>2026-01-01</fecha><proveedor>P001</proveedor><nif>B12345678</nif><pedido>PO-2026-0001</pedido><importe>121.00</importe><estado>PENDIENTE</estado></asiento></asientos></erp>"""


@pytest.mark.parametrize("failure", [401, 429, 500, "timeout"])
def test_erp_recovers(failure, monkeypatch):
    monkeypatch.setattr("alberto.erp.time.sleep", lambda _: None)
    hits = {"login": 0, "data": 0}
    events = []

    def respond(request):
        if request.url.path.endswith("login"):
            hits["login"] += 1
            return httpx.Response(
                200, content=b"<erp><token>secret-session</token></erp>"
            )
        hits["data"] += 1
        if hits["data"] == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("offline", request=request)
            return httpx.Response(failure, headers={"Retry-After": "0"})
        return httpx.Response(200, content=XML.encode("iso-8859-1"))

    client = ERPClient(
        "http://erp.test",
        "user",
        "pass",
        callback=lambda k, p: events.append((k, p)),
        interval=0,
    )
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(respond))
    assert client.snapshot()["total"] == 1
    assert client.retries == 1 and hits["login"] == (2 if failure == 401 else 1)
    assert "secret-session" not in json.dumps(events)
    client.close()


def test_incomplete_snapshot_is_rejected(monkeypatch):
    monkeypatch.setattr("alberto.erp.time.sleep", lambda _: None)
    client = ERPClient("http://erp.test", "user", "pass", interval=0)
    client.token = "token"
    client.client.close()
    client.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=XML.replace("<total>1", "<total>2").encode()
            )
        )
    )
    with pytest.raises(ERPUnavailable, match="incompleto"):
        client.snapshot()
    client.close()


def test_failed_sync_removes_current_not_history(bundle, monkeypatch):
    service, batch, _, _ = bundle
    service.process(batch, ocr=False)

    def fail(self):
        raise ERPUnavailable("fallo simulado")

    monkeypatch.setattr(ERPClient, "snapshot", fail)
    with pytest.raises(ERPUnavailable):
        service.sync_erp(batch, "http://erp.test", "user", "password")
    assert service.batch(batch)["snapshot_id"] is None
    assert service.store.one("SELECT count(*) n FROM decisions")["n"] == 1
    with pytest.raises(ValueError):
        service.export_rows(batch)


def test_ui_routes_csrf_and_local_host(bundle):
    service, batch, _, _ = bundle
    app = create_app(service.store.root)
    with TestClient(app) as client:
        doc = service.store.one("SELECT id FROM documents")["id"]
        assert client.get("/documents/" + doc).status_code == 200  # before extraction
        service.process(batch, ocr=False)
        for url in [
            "/",
            f"/?batch={batch}",
            "/operations",
            "/groups",
            f"/documents/{doc}",
            f"/api/documents/{doc}",
            f"/api/documents/{doc}/pages/1",
            f"/api/batches/{batch}/export",
        ]:
            assert client.get(url).status_code == 200, url
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
        assert client.post(f"/api/batches/{batch}/evaluate").status_code == 403
        payload = {
            "document_ids": [doc],
            "field": "total",
            "value": "125",
            "actor": "Ana",
            "reason": "Verificado en original",
        }
        headers = {"X-CSRF-Token": app.state.service.store.csrf_token}
        assert (
            client.post(
                "/api/reviews/preview", json=payload, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/reviews/commit", json=payload, headers=headers
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/reviews/preview",
                json=payload,
                headers=headers | {"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
