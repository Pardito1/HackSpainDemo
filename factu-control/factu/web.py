from __future__ import annotations

import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymupdf as fitz
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .service import Service
from .erp import ERPUnavailable
from .utils import canonical
from .presentation import FIELDS_ES, RESULTS_ES, EVENTS_ES, euros, greeting, decorate_dashboard

ROOT = Path(__file__).parent


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[str] = Field(min_length=1, max_length=500)
    field: str
    value: str = Field(max_length=120)
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=10, max_length=2000)
    preview_token: str | None = None


class HumanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=20, max_length=2000)
    evidence: str = Field(min_length=10, max_length=2000)
    acknowledged: list[str] = Field(default_factory=list, max_length=100)
    seconds: float = Field(default=0, ge=0, le=14400)
    preview_token: str | None = None


class RetractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=10, max_length=2000)


class ChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=10, max_length=2000)


def create_app(data_dir=None):
    service = Service(data_dir or os.environ.get("FACTU_DATA", "data"))
    app = FastAPI(title="FactU · Mesa de trabajo", version="0.3.0")
    app.state.service = service
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")
    templates.env.filters["euros"] = euros
    templates.env.globals.update(field_labels=FIELDS_ES, result_labels=RESULTS_ES, event_labels=EVENTS_ES, greeting=greeting)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="factu-worker")
    active = {}
    lock = threading.Lock()

    @app.middleware("http")
    async def csrf(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.headers.get("X-CSRF-Token") != service.store.csrf_token:
                return JSONResponse(
                    {"detail": "Token CSRF inválido. Recarga la aplicación."},
                    status_code=403,
                )
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'"
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(ERPUnavailable)
    async def unavailable(request, exc):
        return JSONResponse({"detail": "El ERP no está disponible o su respuesta está incompleta. No se ha publicado una nueva fuente. " + str(exc)}, status_code=503)

    def render(request, name, **context):
        return templates.TemplateResponse(
            request=request,
            name=name,
            context={"csrf": service.store.csrf_token, **context},
        )

    def submit(batch_id, task, function):
        service.batch(batch_id)
        with lock:
            if any(not item["future"].done() for item in active.values()):
                raise HTTPException(
                    409,
                    "Ya hay un trabajo activo. Su estado se conserva en la bandeja.",
                )
            active[batch_id] = {"task": task, "future": executor.submit(function)}
        return {"accepted": True, "task": task}

    def _amount(d):
        # El total llega como texto ("9221.75") porque Decimal no es JSON-serializable;
        # se reconstruye aqui para poder comparar por valor, no por orden de caracteres.
        try:
            return Decimal(d["total"]) if d["total"] is not None else None
        except InvalidOperation:
            return None

    SORTERS = {
        "total_desc": lambda d: (_amount(d) is None, -(_amount(d) or Decimal(0))),
        "total_asc": lambda d: (_amount(d) is None, _amount(d) or Decimal(0)),
        "supplier_asc": lambda d: d["supplier"].casefold(),
        "supplier_desc": lambda d: d["supplier"].casefold(),
    }

    @app.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        batch: str | None = None,
        result: str | None = None,
        q: str = "",
        sort: str = "attention",
        page: int = 1,
    ):
        if batch:
            service.batch(batch)
        data = decorate_dashboard(service, service.dashboard(batch))
        documents = data["documents"]
        if result:
            documents = [
                d
                for d in documents
                if d["result"] == result or result == "PENDING" and not d["result"]
            ]
        if q:
            documents = [
                d
                for d in documents
                if q.casefold() in (d["file_id"] + " " + (d["nif"] or "") + " " + d["supplier"] + " " + (d["order"] or "")).casefold()
            ]
        # "attention" is the order decorate_dashboard already applied; sólo se
        # reordena de verdad si piden explícitamente otra cosa.
        if sort in SORTERS:
            documents = sorted(documents, key=SORTERS[sort], reverse=sort == "supplier_desc")
        total_filtered = len(documents)
        pages = max(1, (total_filtered + 39) // 40)
        page = max(1, min(page, pages))
        documents = documents[(page-1)*40:page*40]
        attention = next((d for d in data["documents"] if d["result"] == "ESCALAR"), None)
        return render(
            request,
            "index.html",
            **(data | {"documents": documents}),
            selected_batch=batch,
            selected_result=result,
            selected_sort=sort,
            query=q,
            current_page=page, total_pages=pages, total_filtered=total_filtered,
            attention=attention,
        )

    @app.get("/documents/{doc_id}", response_class=HTMLResponse)
    def detail(request: Request, doc_id: str):
        data = service.detail(doc_id)
        return render(request, "detail.html", **data, selected_batch=data["document"]["batch_id"])

    @app.get("/sources", response_class=HTMLResponse)
    def sources(request: Request, batch: str | None = None, change: str | None = None):
        batches = service.store.all("SELECT * FROM batches ORDER BY created DESC")
        batch = batch or (batches[0]["id"] if batches else None)
        data = service.source_workspace(batch) if batch else {}
        material_path = ROOT / "materials.json"
        return render(request, "sources.html", **data, batches=batches, selected_batch=batch,
                      focused_change=change, materials=json.loads(material_path.read_text()) if material_path.exists() else None)

    @app.get("/operations", response_class=HTMLResponse)
    def operations(request: Request, batch: str | None = None):
        data = service.dashboard(batch)
        return render(
            request,
            "operations.html",
            **data,
            audit=service.store.verify_audit(),
            events=service.store.all("SELECT * FROM events ORDER BY id DESC LIMIT 100"),
            selected_batch=batch,
        )

    @app.get("/groups", response_class=HTMLResponse)
    def groups(request: Request, batch: str | None = None):
        return render(
            request,
            "groups.html",
            groups=[g for g in service.groups(batch) if len(g["documents"]) > 1],
            drafts=service.consultation_drafts(batch),
            selected_batch=batch,
        )

    @app.get("/api/consultations/{draft_id}/draft")
    def consultation_draft(draft_id: str, batch: str | None = None):
        draft = next((d for d in service.consultation_drafts(batch) if d["id"] == draft_id), None)
        if draft is None:
            raise HTTPException(404, "La consulta ya no tiene facturas pendientes. Actualiza la vista.")
        return Response(draft["draft"], media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="consulta-proveedor.txt"'})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.3.0"}

    @app.get("/api/batches/{batch_id}/status")
    def status(batch_id: str):
        data = service.dashboard(batch_id)
        task = active.get(batch_id)
        run = {
            "active": bool(task and not task["future"].done()),
            "task": task["task"] if task else None,
        }
        if task and task["future"].done():
            try:
                run["result"] = task["future"].result()
            except BaseException as exc:
                run["error"] = str(exc)
        return {"metrics": data["metrics"], "run": run}

    @app.post("/api/batches")
    async def ingest(
        name: str = Form(...),
        as_of: str = Form(...),
        workbook: UploadFile = File(...),
        files: list[UploadFile] = File(...),
    ):
        if len(files) > 2000:
            raise HTTPException(400, "Máximo 2000 documentos por lote")
        with tempfile.TemporaryDirectory(prefix="factu-import-") as temp:
            folder = Path(temp) / "pdfs"
            folder.mkdir()
            master = Path(temp) / "master.xlsx"
            content = await workbook.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(400, "Excel demasiado grande")
            master.write_bytes(content)
            for upload in files:
                filename = upload.filename or ""
                if (
                    filename != Path(filename).name
                    or not filename.lower().endswith(".pdf")
                    or (folder / filename).exists()
                ):
                    raise HTTPException(400, "Nombres PDF inválidos o repetidos")
                content = await upload.read(50 * 1024 * 1024 + 1)
                if len(content) > 50 * 1024 * 1024:
                    raise HTTPException(400, "PDF demasiado grande")
                (folder / filename).write_bytes(content)
            return service.ingest(folder, master, name, as_of)

    @app.post("/api/batches/{batch_id}/sync")
    def sync(batch_id: str):
        return submit(
            batch_id,
            "ERP",
            lambda: service.sync_erp(
                batch_id,
                os.getenv("ERP_URL", "http://127.0.0.1:8009"),
                os.getenv("ERP_USER", "alberto"),
                os.getenv("ERP_PASSWORD", "FACTURAS2009"),
            ),
        )

    @app.post("/api/batches/{batch_id}/process")
    def process(batch_id: str):
        return submit(batch_id, "Procesar", lambda: service.process(batch_id))

    @app.post("/api/batches/{batch_id}/retry")
    def retry(batch_id: str):
        service.retry(batch_id)
        return submit(batch_id, "Recuperar", lambda: service.process(batch_id))

    @app.post("/api/batches/{batch_id}/evaluate")
    def reevaluate(batch_id: str):
        return submit(batch_id, "Reevaluar", service.reevaluate_all)

    @app.post("/api/reviews/preview")
    def preview(body: ReviewRequest):
        return service.preview_review(
            body.document_ids, body.field, body.value, body.actor, body.reason
        )

    @app.post("/api/reviews/commit")
    def commit(body: ReviewRequest):
        if not body.preview_token:
            raise ValueError("Primero simula el resultado")
        return service.commit_review(
            body.document_ids,
            body.field,
            body.value,
            body.actor,
            body.reason,
            body.preview_token,
        )

    @app.post("/api/documents/{doc_id}/answer/preview")
    def human_preview(doc_id: str, body: HumanRequest):
        return service.human_preview(doc_id, **body.model_dump(exclude={"preview_token"}))

    @app.post("/api/documents/{doc_id}/answer/commit")
    def human_commit(doc_id: str, body: HumanRequest):
        if not body.preview_token:
            raise ValueError("Primero revisa el efecto de tu respuesta")
        return service.human_commit(doc_id, **body.model_dump())

    @app.post("/api/documents/{doc_id}/answer/retract")
    def human_retract(doc_id: str, body: RetractRequest):
        return service.retract_human_answer(doc_id, body.actor, body.reason)

    @app.post("/api/batches/{batch_id}/changes/upload")
    async def change_upload(batch_id: str, kind: str = Form(...), actor: str = Form(...),
                            reason: str = Form(...), rules_ack: bool = Form(False), file: UploadFile = File(...)):
        if kind not in ("master", "policy") or len(actor) > 120 or len(reason) > 2000:
            raise ValueError("Tipo, responsable o motivo inválido")
        content = await file.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("Archivo demasiado grande")
        with tempfile.TemporaryDirectory(prefix="factu-source-") as temp:
            # Keep only a filename, never allow a client supplied path.
            suffix = ".xlsx" if kind == "master" else ".json"
            path = Path(temp) / (Path(file.filename or ("fuente"+suffix)).name)
            if path.suffix.lower() != suffix:
                raise ValueError("La extensión no corresponde al tipo de fuente")
            path.write_bytes(content)
            return service.prepare_upload(batch_id, path, kind, actor, reason, rules_ack)

    @app.post("/api/batches/{batch_id}/changes/erp")
    def change_erp(batch_id: str, body: ChangeRequest):
        return service.prepare_erp(batch_id, os.getenv("ERP_URL", "http://127.0.0.1:8009"),
            os.getenv("ERP_USER", "alberto"), os.getenv("ERP_PASSWORD", "FACTURAS2009"), body.actor, body.reason)

    @app.post("/api/changes/{change_id}/commit")
    def change_commit(change_id: str):
        return service.commit_source(change_id)

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str):
        return service.detail(doc_id)

    @app.get("/api/sources/{source_id}")
    def source(source_id: str):
        data = service.store.source(source_id)
        data.pop("blob", None)
        return data

    @app.get("/sources/{source_id}", response_class=HTMLResponse)
    def source_detail(request: Request, source_id: str, batch: str | None = None):
        data = service.store.source(source_id)
        if "suppliers" in data and "orders" in data:
            kind = "master"
        elif "rows" in data and "pages" in data:
            kind = "erp"
        elif "tolerance_eur" in data:
            kind = "policy"
        else:
            kind = "unknown"
        return render(
            request,
            "source_detail.html",
            source_id=source_id,
            kind=kind,
            data=data,
            selected_batch=batch,
        )

    @app.get("/api/documents/{doc_id}/original")
    def original(doc_id: str):
        doc = service.document(doc_id)
        return FileResponse(
            doc["path"],
            media_type="application/pdf",
            filename=doc["file_id"],
            content_disposition_type="attachment",
        )

    @app.get("/api/documents/{doc_id}/pages/{page_number}")
    def page(doc_id: str, page_number: int):
        doc = service.document(doc_id)
        with fitz.open(doc["path"]) as pdf:
            if not 1 <= page_number <= len(pdf):
                raise HTTPException(404, "Página no encontrada")
            return Response(
                pdf[page_number - 1]
                .get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                .tobytes("png"),
                media_type="image/png",
            )

    @app.get("/api/batches/{batch_id}/export")
    def export(batch_id: str, filename: str = "outcomes.jsonl"):
        if filename not in ("outcomes.jsonl", "outcomes_lote2.jsonl"):
            raise ValueError("Nombre de entrega inválido")
        rows = service.export_rows(batch_id)
        return Response(
            "".join(canonical(r) + "\n" for r in rows),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
