from __future__ import annotations

import importlib.metadata
import re
import threading
import time
from collections import defaultdict
from functools import lru_cache

import pymupdf as fitz

from . import modelo
from .utils import clean, digest, identifier, invoice_date, money

VERSION = "native-rapidocr-4"
FIELDS = (
    "invoice_number",
    "supplier_nif",
    "iban",
    "order",
    "date",
    "base",
    "tax_rate",
    "tax_amount",
    "total",
)
_ocr = None
_ocr_lock = threading.Lock()


def invoice_number(value):
    """Do not turn an OCR concatenation into an apparently valid identifier."""
    value = identifier(value)
    if (len(value) > 80 or not re.fullmatch(r"[A-Z0-9][A-Z0-9/_-]{2,}", value)
            or re.search(r"FECHA|DATE|IBAN|TOTAL|PEDIDO|NIF|CIF", value)
            or not re.search(r"\d", value)):
        raise ValueError("Número de factura ambiguo: contiene etiquetas o campos mezclados")
    return value


@lru_cache(maxsize=1)
def engine_versions():
    try:
        package = importlib.metadata.distribution("rapidocr-onnxruntime")
        from pathlib import Path

        models = Path(package.locate_file("rapidocr_onnxruntime/models"))
        artifacts = {
            p.name: digest(p.read_bytes()) for p in sorted(models.glob("*.onnx"))
        }
        ocr_version = package.version
    except importlib.metadata.PackageNotFoundError:
        ocr_version, artifacts = None, {}
    return {
        "pymupdf": fitz.VersionBind,
        "rapidocr": ocr_version,
        "ocr_model_hashes": artifacts,
    }


def union(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def group_lines(tokens, page_number, method):
    groups = []
    for token in sorted(
        tokens, key=lambda t: ((t["bbox"][1] + t["bbox"][3]) / 2, t["bbox"][0])
    ):
        box = token["bbox"]
        y = (box[1] + box[3]) / 2
        target = next(
            (
                g
                for g in reversed(groups[-3:])
                if abs(g["y"] - y) < max(3, (box[3] - box[1]) * 0.45)
            ),
            None,
        )
        if target is None:
            target = {"y": y, "tokens": []}
            groups.append(target)
        target["tokens"].append(token)
    lines = []
    for group in groups:
        words = sorted(group["tokens"], key=lambda t: t["bbox"][0])
        text = ""
        for token in words:
            token["start"] = len(text)
            text += clean(token["text"])
            token["end"] = len(text)
            text += " "
        lines.append(
            {
                "text": text.strip(),
                "raw_text": " ".join(t["text"] for t in words),
                "words": words,
                "bbox": union([t["bbox"] for t in words]),
                "page": page_number,
                "method": method,
            }
        )
    return lines


def ocr_page(page, scale=3):
    global _ocr
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError("OCR no instalado: pip install '.[ocr]'") from exc
    with _ocr_lock:
        if _ocr is None:
            _ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        result, _ = _ocr(image)
    tokens = []
    for polygon, text, confidence in result or []:
        xs, ys = [p[0] / scale for p in polygon], [p[1] / scale for p in polygon]
        tokens.append(
            {
                "text": text,
                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                "confidence": float(confidence),
            }
        )
    return tokens


def parse_fields(lines):
    candidates = defaultdict(list)

    def candidate(field, raw, line, span, normalize):
        if not raw.strip():
            return
        words = [
            w for w in line["words"] if w["end"] > span[0] and w["start"] < span[1]
        ]
        bbox = union([w["bbox"] for w in words]) if words else line["bbox"]
        scores = [w["confidence"] for w in words if w.get("confidence") is not None]
        value, error = None, None
        try:
            value = str(normalize(raw))
        except (ValueError, ArithmeticError) as exc:
            error = str(exc)
        candidates[field].append(
            {
                "raw_value": raw,
                "value": value,
                "error": error,
                "page": line["page"],
                "bbox": bbox,
                "coordinate_space": "pdf_points_top_left",
                "method": line["method"],
                "confidence": min(scores) if scores else None,
                "source_text": line["raw_text"],
                "transformations": [
                    "unicode_NFKC_format_char_removal",
                    normalize.__name__,
                ],
            }
        )

    date_pattern = r"\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{1,2}\s+de\s+\w+\s+de\s+\d{4}"
    for line in lines:
        s = line["text"]
        for m in re.finditer(
            r"(?:ref\.?\s*factura|n[ºo°]?\s*(?:de\s*)?factura|factura(?:\s+simplificada)?(?:\s*n[ºo°])?|invoice\s*#?)\s*[:#]?\s*([A-Z0-9][A-Z0-9/_-]{2,})",
            s,
            re.I,
        ):
            if re.search(r"(?:fecha|total|importe|base)\s*$", s[: m.start()], re.I) or re.fullmatch(
                date_pattern, m[1], re.I
            ):
                continue  # "Fecha factura" / "Total factura" are labels, not a second invoice number.
            if re.match(r"[,.]\d{2}\b", s[m.end(1):]):
                continue  # "Total factura: 535,35": an amount, not an identifier.
            if re.search(r"\d", m[1]):
                # Split only a recognizable adjacent date label; preserve raw line
                # and token coordinates so a person can inspect the separation.
                adjacent = re.search(r"(?:fecha|date)(?=[:.\s]*\d)", m[1], re.I)
                end = adjacent.start() if adjacent else len(m[1])
                candidate("invoice_number", m[1][:end], line,
                          (m.start(1), m.start(1) + end), invoice_number)
                if adjacent and candidates["invoice_number"]:
                    candidates["invoice_number"][-1]["transformations"].append("split_adjacent_date_label")
        for m in re.finditer(r"\bPO\s*[-–]\s*\d{4}\s*[-–]\s*\d{3,6}\b", s, re.I):
            candidate("order", m[0], line, m.span(), identifier)
        for m in re.finditer(
            r"(?:fecha(?:\s+de\s+emisi[oó]n|\s+factura)?|date)\s*[:.]?\s*("
            + date_pattern
            + r")",
            s,
            re.I,
        ):
            candidate("date", m[1], line, m.span(1), invoice_date)
        if not re.search(r"cliente|destinatario|facturar\s+a|bill\s+to", s, re.I):
            for m in re.finditer(
                r"(?:NIF|CIF|Tax\s*ID|VAT\s*ID)\s*[:.]?\s*([A-Z]\s*\d{7}\s*[A-Z0-9]|\d{8}[A-Z])\b",
                s,
                re.I,
            ):
                candidate("supplier_nif", m[1], line, m.span(1), identifier)
        if re.search(r"[I1l]BAN|cuenta\s+de\s+abono", s, re.I):
            for m in re.finditer(r"\b(ES\s*\d{2}(?:\s*\d){20})(?!\d)", s, re.I):
                candidate("iban", m[1], line, m.span(1), identifier)
        for field, label in (
            ("base", r"^(?:base(?:\s+imponible)?|importe\s+base|subtotal)\b"),
            ("total", r"^(?:importe\s+total|total(?:\s+factura|\s+a\s+pagar)?)\b"),
            ("tax_amount", r"^(?:cuota\s+)?(?:I\.?V\.?A\.?|VAT|tax)(?=\s|[(:.\d]|$)"),
        ):
            label_match = re.search(label, s, re.I)
            if not label_match:
                continue
            # A payable amount must be printed as an amount, not a year/rate in prose.
            amounts = list(
                re.finditer(r"(?<![\w.,])[+-]?\d[\d.,]*[.,]\d{2}(?![\d.,])", s)
            )
            if amounts:
                m = amounts[-1]
                candidate(field, m[0], line, m.span(), money)
            if field == "tax_amount":
                for m in re.finditer(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", s):
                    candidate("tax_rate", m[1], line, m.span(1), money)
    fields = {}
    for field in FIELDS:
        choices = candidates[field]
        distinct = {c["value"] for c in choices if c["value"] is not None}
        errors = [c for c in choices if c["error"]]
        status = (
            "MISSING"
            if not choices
            else "INVALID" if errors else "CONFLICT" if len(distinct) != 1 else "OK"
        )
        selected = choices[0] if status == "OK" else None
        if selected and any(
            c["confidence"] is not None and c["confidence"] < 0.85 for c in choices
        ):
            status = "LOW_QUALITY"
        fields[field] = {
            "value": selected["value"] if selected else None,
            "status": status,
            "evidence": choices,
        }
    # EUR is a declared task context, not an invented visible symbol; other printed currencies block.
    currencies = sorted(
        set(
            re.findall(
                r"\b(?:EUR|USD|GBP|CHF)\b|€|\$|£", "\n".join(l["text"] for l in lines)
            )
        )
    )
    normalized = sorted(
        {{"€": "EUR", "$": "USD", "£": "GBP"}.get(v, v) for v in currencies}
    )
    fields["currency"] = {
        "value": (
            normalized[0] if len(normalized) == 1 else "EUR" if not normalized else None
        ),
        "status": "OK" if len(normalized) <= 1 else "CONFLICT",
        "evidence": [],
        "assumption": "moneda EUR del caso" if not normalized else None,
    }
    return fields


_NORMALIZADORES_MODELO = {
    "invoice_number": invoice_number,
    "supplier_nif": identifier,
    "iban": identifier,
    "order": identifier,
    "date": invoice_date,
    "base": modelo.normalizar_importe,
    "tax_amount": modelo.normalizar_importe,
    "total": modelo.normalizar_importe,
    "tax_rate": modelo.normalizar_tipo,
}


def fusionar_modelo(fields, campos):
    """El modelo solo aporta candidatos: sin OK previo resuelve; si contradice
    una lectura OK, CONFLICT. Una lectura que no supera la validación entra
    como INVALID con su motivo y la política la escalará."""
    for field in FIELDS:
        entrada = campos.get(field)
        if not entrada or entrada.get("raw_value") is None:
            continue
        normalize = _NORMALIZADORES_MODELO[field]
        raw, evidencia = str(entrada["raw_value"]), entrada.get("evidencia")
        value, error = None, None
        try:
            value = str(normalize(raw))
        except (ValueError, ArithmeticError) as exc:
            error = str(exc)
        if error is None:
            motivo = modelo.validar_lectura_modelo(field, value, evidencia)
            if motivo:
                value, error = None, motivo
        fact = fields[field]
        fact["evidence"].append(
            {
                "raw_value": raw,
                "value": value,
                "error": error,
                "page": entrada.get("page"),
                "bbox": None,
                "coordinate_space": None,
                "method": "modelo",
                "confidence": None,
                "source_text": evidencia,
                "transformations": ["modelo", normalize.__name__],
            }
        )
        if fact["status"] == "OK":
            if value is not None and value != fact["value"]:
                fact["status"], fact["value"] = "CONFLICT", None
        elif value is not None:
            fact["status"], fact["value"] = "OK", value
        elif fact["status"] == "MISSING":
            fact["status"] = "INVALID"


def extract_pdf(path, ocr=True):
    start = time.monotonic()
    pages, lines, warnings = [], [], []
    with fitz.open(path) as doc:
        if doc.needs_pass or not 1 <= len(doc) <= 100:
            raise ValueError("PDF protegido, vacío o con más de 100 páginas")
        for i, page in enumerate(doc):
            tokens = [
                {"text": w[4], "bbox": list(w[:4]), "confidence": None}
                for w in page.get_text("words")
            ]
            native_length = sum(len(t["text"]) for t in tokens)
            image_area = sum(
                r.width * r.height
                for image in page.get_images()
                for r in page.get_image_rects(image[0])
            )
            needs_ocr = (
                native_length < 60
                or image_area > page.rect.width * page.rect.height * 0.45
            )
            method = "pymupdf"
            if needs_ocr and ocr:
                try:
                    ocr_tokens = ocr_page(page)
                    if ocr_tokens:
                        tokens, method = ocr_tokens, "rapidocr-onnxruntime"
                    else:
                        warnings.append({"code": "OCR_EMPTY", "page": i + 1})
                except (ImportError, RuntimeError) as exc:
                    warnings.append(
                        {"code": "OCR_UNAVAILABLE", "page": i + 1, "message": str(exc)}
                    )
            elif needs_ocr:
                warnings.append({"code": "OCR_DISABLED", "page": i + 1})
            page_lines = group_lines(tokens, i + 1, method)
            lines.extend(page_lines)
            pages.append(
                {
                    "number": i + 1,
                    "width": page.rect.width,
                    "height": page.rect.height,
                    "method": method,
                    "text": "\n".join(l["text"] for l in page_lines),
                    "needs_ocr": needs_ocr,
                }
            )
    fields = parse_fields(lines)
    model_usage = None
    pendientes = [p["number"] for p in pages if p["needs_ocr"]]
    incompletos = [
        f for f in FIELDS if f != "invoice_number" and fields[f]["status"] != "OK"
    ]
    if ocr and pendientes and incompletos:
        lectura = modelo.leer_campos(path, pendientes)
        if "error" in lectura:
            warnings.append(
                {
                    "code": "MODELO_NO_DISPONIBLE",
                    "message": lectura["error"]
                    + (": " + lectura["detalle"] if lectura.get("detalle") else ""),
                    "fields": incompletos,
                }
            )
        else:
            fusionar_modelo(fields, lectura["campos"])
            model_usage = lectura["uso"]
    flagged = [
        {"page": l["page"], "bbox": l["bbox"], "text": l["text"]}
        for l in lines
        if re.search(
            r"agente|ignora[rd]?|no\s+registres|hardcode|equipo\s+de\s+evaluaci[oó]n|no\s+recalcular|debe\s+marcarse"
            r"|ignore\s+(?:all|previous|the|prior)|system\s*(?:message|prompt|:)"
            r"|mark\s+(?:as\s+)?(?:PAGAR|NO_PAGAR|paid)|do\s+not\s+(?:log|record)"
            r"|<\s*script\b|\b(?:curl|wget)\s+https?://|\b(?:execute|ejecuta)\b",
            l["text"],
            re.I,
        )
    ]
    out = {
        "version": VERSION,
        "fields": fields,
        "pages": pages,
        "warnings": warnings,
        "untrusted_instructions": flagged,
        "seconds": time.monotonic() - start,
        "engines": engine_versions(),
    }
    if model_usage:
        out["model_usage"] = model_usage
    return out
