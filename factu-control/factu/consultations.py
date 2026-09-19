"""Supplier questions from an explicit allowlist, never from document instructions.

This is a communication aid, not a payment authority. Only a verified currency
confirmation can be shared; bank details and monetary corrections stay individual.
"""
import json
import re
from decimal import Decimal, InvalidOperation

from .utils import clean, digest

TOPICS = {
    "currency": ("Moneda de la factura", "¿En qué moneda están emitidas estas facturas? Indicad la moneda y las referencias a las que se aplica.", "currency"),
    "amounts": ("Importes y desglose", "Necesitamos confirmar el importe y su desglose (base, IVA y total). Si hay un error, aportad la factura corregida.", None),
    "date": ("Fecha de emisión", "Necesitamos confirmar la fecha de emisión. Si hay un error, aportad la factura corregida.", None),
    "invoice_number": ("Referencia de factura", "Necesitamos el número de factura para identificar estos documentos.", None),
}


def amount_summary(documents):
    totals, unknown = {}, 0
    for doc in documents:
        try:
            value = Decimal(str(doc["total"]))
            if not doc["amount_known"] or not value.is_finite():
                raise InvalidOperation
            code = doc["currency"]
            totals[code] = totals.get(code, Decimal(0)) + value
        except (InvalidOperation, TypeError, KeyError):
            unknown += 1
    return {"totals": {k: str(v) for k, v in sorted(totals.items())}, "unknown": unknown}


def workspace(service, batch_id=None):
    if batch_id:
        service.batch(batch_id)
    rows = service.store.all(
        "SELECT d.id,d.file_id,d.batch_id,x.payload FROM documents d "
        "JOIN decisions x ON x.id=d.latest_decision WHERE x.result='ESCALAR'"
        + (" AND d.batch_id=?" if batch_id else "") + " ORDER BY d.file_id",
        (batch_id,) if batch_id else (),
    )
    masters, groups, internal_ids, external_ids = {}, {}, set(), set()
    for row in rows:
        decision = json.loads(row["payload"])
        fields = decision["fields"]
        failed = {r["id"] for r in decision["rules"] if r["state"] != "PASS"}
        nif = fields.get("supplier_nif", {})
        if row["batch_id"] not in masters:
            masters[row["batch_id"]] = service.store.source(service.batch(row["batch_id"])["master_id"])
        suppliers = {(s["id"], s["name"], s["iban"]) for group in masters[row["batch_id"]]["suppliers"].values()
                     for s in group if s["nif"] == nif.get("value")}
        # Unknown identity, unsafe text or incomplete reading require internal review first.
        if (nif.get("status") != "OK" or len(suppliers) != 1
                or failed & {"document_instructions", "document_coverage", "supplier_identity"}
                or decision.get("human_response_stale")):
            internal_ids.add(row["id"])
            continue
        topics = set()
        if "currency" in failed:
            topics.add("currency")
        if failed & {"amount_matches_order", "tax_arithmetic", "total_arithmetic"}:
            # Check the original internally first when a read is uncertain.
            if all(fields.get(k, {}).get("status") == "OK" for k in ("base", "tax_rate", "tax_amount", "total")):
                topics.add("amounts")
        if "invoice_date" in failed and fields.get("date", {}).get("status") == "OK":
            topics.add("date")
        for key, topic in (("invoice_number", "invoice_number"), ("date", "date"), ("total", "amounts")):
            if "field:" + key in failed and fields.get(key, {}).get("status") == "MISSING":
                topics.add(topic)
        handled = {"currency"} if "currency" in topics else set()
        if "amounts" in topics:
            handled |= {"amount_matches_order", "tax_arithmetic", "total_arithmetic", "field:total"}
        if "date" in topics:
            handled |= {"invoice_date", "field:date"}
        if "invoice_number" in topics:
            handled.add("field:invoice_number")
        if failed - handled or not topics:
            internal_ids.add(row["id"])
        if not topics:
            continue
        supplier_id, name, _ = next(iter(suppliers))
        key = digest({"nif": nif["value"], "identity": sorted(suppliers)})[:16]
        group = groups.setdefault(key, {"id": key, "supplier": name, "nif": nif["value"], "documents": [], "topics": {}})
        total, currency = fields.get("total", {}), fields.get("currency", {})
        doc = {"id": row["id"], "file_id": row["file_id"], "total": total.get("value"), "currency": currency.get("value"),
               "amount_known": total.get("status") == currency.get("status") == "OK" and bool(currency.get("value")),
               "current_currency": currency.get("value") if currency.get("status") == "OK" else None,
               "internal": row["id"] in internal_ids}
        group["documents"].append(doc)
        external_ids.add(row["id"])
        for topic in sorted(topics):
            title, question, field = TOPICS[topic]
            item = group["topics"].setdefault(topic, {"id": topic, "title": title, "question": question, "field": field, "documents": []})
            item["documents"].append(doc)
    result = sorted(groups.values(), key=lambda g: (-len(g["documents"]), g["supplier"], g["id"]))
    for group in result:
        group["topics"] = list(group["topics"].values())
        group["amounts"] = amount_summary(group["documents"])
        group["priority"] = "high" if len(group["documents"]) >= 10 else "normal"
        group["priority_label"] = "Alta · 10 o más facturas" if group["priority"] == "high" else "Normal · menos de 10 facturas"
        # Fixed questions are not copied from untrusted document text.
        lines = ["BORRADOR PARA REVISAR — NO ENVIADO", "", "Asunto: Aclaraciones de facturas — " + clean(group["supplier"]), "", "Hola,", "", "Necesitamos aclarar estos puntos:", ""]
        for topic in group["topics"]:
            lines += [topic["title"], topic["question"]]
            lines += ["- " + clean(d["file_id"]) for d in topic["documents"]]
            lines.append("")
        lines += ["Por favor, indicad la referencia que respalda la respuesta y las facturas a las que se aplica.", "Este mensaje no autoriza pagos ni cambios de cuenta.", "", "Gracias,", "Administración"]
        group["draft"] = "\n".join(lines)
    return {"drafts": result, "supplier_count": len(result), "invoice_count": len(external_ids),
            "priority_count": sum(g["priority"] == "high" for g in result), "internal_count": len(internal_ids),
            "amounts": amount_summary([d for g in result for d in g["documents"]])}


def response_preview(service, group_id, topic_id, document_ids, value, actor, response, reference, verified, batch_id=None):
    if verified is not True or len(clean(response)) < 10 or len(clean(reference)) < 5:
        raise ValueError("Registra la respuesta, su referencia y confirma que la has verificado.")
    if not re.fullmatch(r"[A-Za-z]{3}", value.strip()):
        raise ValueError("Indica un código de moneda de tres letras, como EUR o USD.")
    group = next((g for g in workspace(service, batch_id)["drafts"] if g["id"] == group_id), None)
    topic = next((t for t in group["topics"] if t["id"] == topic_id), None) if group else None
    if not topic or topic["field"] != "currency":
        raise ValueError("Esta consulta no admite una confirmación compartida. Revisa cada expediente.")
    scope = {d["id"] for d in topic["documents"]}
    if not document_ids or not set(document_ids) <= scope:
        raise ValueError("Selecciona solo facturas que tengan esta consulta pendiente con este proveedor.")
    reason = f"Respuesta verificada del proveedor. Referencia: {clean(reference)}. Respuesta: {clean(response)}"
    preview = service.preview_review(document_ids, "currency", value, actor, reason)
    docs = {d["id"]: d for d in topic["documents"]}
    for item in preview["previews"]:
        item.update(field="Moneda", current=docs[item["id"]]["current_currency"], proposed=preview["value"], reference=clean(reference))
    preview["review_token"] = preview["preview_token"]
    preview["preview_token"] = digest({"preview": preview, "group": group_id, "topic": topic_id,
        "decisions": [(d, service.document(d)["latest_decision"]) for d in preview["ids"]], "code": service.code_sha256})
    return preview
