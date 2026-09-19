from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from .utils import digest, now


class ERPUnavailable(RuntimeError):
    pass


class ERPClient:
    def __init__(
        self,
        url,
        user,
        password,
        callback=None,
        timeout=10,
        max_attempts=5,
        interval=0.15,
    ):
        parsed = urlparse(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("URL ERP inválida")
        self.url = url.rstrip("/")
        self.user, self.password = user, password
        self.callback = callback or (lambda *a, **kw: None)
        self.client = httpx.Client(
            timeout=timeout, follow_redirects=False, trust_env=False
        )
        self.token = None
        self.max_attempts, self.interval = max_attempts, interval
        self.last_call = 0.0
        self.attempts = 0
        self.retries = 0

    def close(self):
        self.client.close()

    def _request(self, path, login=False):
        for attempt in range(1, self.max_attempts + 1):
            if not login and not self.token:
                self._login()
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            start = time.monotonic()
            self.last_call = start
            status = "timeout"
            retry_after = None
            try:
                response = (
                    self.client.post(
                        self.url + path,
                        data={"usuario": self.user, "clave": self.password},
                    )
                    if login
                    else self.client.get(
                        self.url + path, headers={"X-ERP-Token": self.token}
                    )
                )
                status = response.status_code
                self.attempts += 1
                self.callback(
                    "erp_request",
                    {
                        "path": path,
                        "attempt": attempt,
                        "status": status,
                        "seconds": time.monotonic() - start,
                    },
                )
                if status == 200:
                    try:
                        root = ET.fromstring(response.content)
                    except ET.ParseError as exc:
                        raise ERPUnavailable("XML ERP inválido") from exc
                    return root, response.content
                if status == 401 and not login:
                    self.token = None
                elif status in (429, 500, 502, 503, 504):
                    raw = response.headers.get("Retry-After")
                    if raw:
                        try:
                            retry_after = max(0, float(raw))
                        except ValueError:
                            retry_after = max(
                                0,
                                (
                                    parsedate_to_datetime(raw)
                                    - datetime.now(timezone.utc)
                                ).total_seconds(),
                            )
                else:
                    raise ERPUnavailable(f"ERP HTTP {status} en {path}")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                self.attempts += 1
                self.callback(
                    "erp_request",
                    {
                        "path": path,
                        "attempt": attempt,
                        "status": type(exc).__name__,
                        "seconds": time.monotonic() - start,
                    },
                )
            if attempt < self.max_attempts:
                self.retries += 1
                delay = (
                    retry_after
                    if retry_after is not None
                    else min(0.2 * 2 ** (attempt - 1), 5) + random.uniform(0, 0.05)
                )
                # Do not retry before a long Retry-After; defer the entire sync instead.
                if delay > 30:
                    raise ERPUnavailable(
                        f"ERP solicita espera de {delay:.0f}s; sincronización aplazada"
                    )
                time.sleep(delay)
        raise ERPUnavailable(
            f"ERP no disponible tras {self.max_attempts} intentos en {path}"
        )

    def _login(self):
        root, _ = self._request("/erp/login", login=True)
        self.token = root.findtext("token")
        if not self.token:
            raise ERPUnavailable("Login sin token")

    def snapshot(self):
        started = time.monotonic()
        first, raw = self._request("/erp/asientos?pagina=1")
        try:
            pages, total = int(first.findtext("meta/paginas")), int(
                first.findtext("meta/total")
            )
        except (TypeError, ValueError) as exc:
            raise ERPUnavailable("Metadatos de paginación inválidos") from exc
        if not 1 <= pages <= 100000 or total < 0:
            raise ERPUnavailable("Paginación fuera de límites")
        records, responses = [], []
        for page in range(1, pages + 1):
            root, content = (
                (first, raw)
                if page == 1
                else self._request(f"/erp/asientos?pagina={page}")
            )
            if (
                int(root.findtext("meta/total", "-1")) != total
                or int(root.findtext("meta/paginas", "-1")) != pages
            ):
                raise ERPUnavailable(
                    "El ERP cambió durante la paginación; repetir snapshot"
                )
            records.extend(
                {c.tag: c.text or "" for c in row}
                for row in root.findall("asientos/asiento")
            )
            responses.append(
                {
                    "page": page,
                    "sha256": digest(content),
                    "xml": content.decode("iso-8859-1"),
                }
            )
        if len(records) != total or len({r.get("id") for r in records}) != total:
            raise ERPUnavailable("Snapshot incompleto o asientos duplicados")
        required = {"id", "fecha", "proveedor", "nif", "pedido", "importe", "estado"}
        if any(
            not required.issubset(r) or not r["id"] or not r["pedido"] for r in records
        ):
            raise ERPUnavailable("Esquema ERP incompleto")
        return {
            "rows": records,
            "pages": responses,
            "total": total,
            "created": now(),
            "url": self.url,
            "complete": True,
            "seconds": time.monotonic() - started,
            "attempts": self.attempts,
            "retries": self.retries,
        }
