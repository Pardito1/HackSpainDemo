"""Plain-language labels. Presentation never modifies source facts or decisions."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json

from .human_guards import payment_blockers

FIELDS_ES = {"invoice_number":"Número de factura", "supplier_nif":"NIF del proveedor",
    "iban":"Cuenta bancaria (IBAN)", "order":"Pedido", "date":"Fecha de emisión",
    "base":"Base imponible", "tax_rate":"Tipo de IVA", "tax_amount":"Cuota de IVA",
    "total":"Total", "currency":"Moneda"}
RESULTS_ES = {"PAGAR":"Propuesta de pago", "NO_PAGAR":"No pagar", "ESCALAR":"Requiere revisión",
    "PENDING":"Por procesar", "WAITING_ERP":"Esperando al ERP", "RECEIVED":"Recibida",
    "EXTRACTED":"Por comprobar", "HUMAN_REVIEW":"Requiere revisión", "DECIDED":"Comprobada",
    "RUNNING":"En proceso", "ERROR":"Requiere recuperación", "RETRY_WAIT":"Reintento pendiente"}
RESULTS_ES["ERP_ERROR"] = "Consulta contable interrumpida"
EVENTS_ES = {"decision_published":"Resultado registrado", "human_correction":"Lectura corregida",
    "alberto_answered":"Respuesta registrada", "decision_reused":"Decisión conservada tras verificar el cambio",
    "source_change_requires_review":"Un cambio requiere revisar esta factura", "extraction_completed":"Lectura terminada",
    "source_change_applied":"Nueva fuente aplicada", "source_change_previewed":"Impacto calculado",
    "erp_snapshot_published":"ERP sincronizado", "batch_ingested":"Lote registrado",
    "erp_request_retry":"Consulta ERP reintentada", "worker_run":"Procesamiento terminado"}

def greeting(hour=None):
    """Saludo segun la hora local de la maquina que sirve la app.

    Herramienta local de un solo operador (ver README): el reloj del
    servidor es el mismo que el de quien la usa, así que no hace falta
    la hora del navegador.
    """
    hour = datetime.now().hour if hour is None else hour
    if 6 <= hour < 14:
        return "Buenos días,"
    if 14 <= hour < 21:
        return "Buenas tardes,"
    return "Buenas noches,"

def euros(value):
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return "Por confirmar"
        return f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (ValueError, InvalidOperation):
        return str(value)


def readable_date(value):
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y · %H:%M:%S")
    except (ValueError, TypeError):
        return value or "Fecha no disponible"


def invoice_activity(data):
    """Describe actions actually recorded; a correction is never an approval."""
    raw_fields = (data.get("extraction") or {}).get("fields", {})
    values = {key: field.get("value") for key, field in raw_fields.items()}
    versions = {row["id"]: json.loads(row["payload"]) for row in data["history"]}
    activity, corrections = [], []
    first_check = True
    previous_decision = None
    for event in reversed(data["events"]):
        payload, kind = event["payload"], event["kind"]
        item = {"date": readable_date(event["created"]), "reason": "", "evidence": "", "changes": []}
        if kind == "human_correction":
            key, value = payload["field"], payload["value"]
            changed = values.get(key) != value
            field_name = {"iban": "el IBAN", "currency": "la moneda", "supplier_nif": "el NIF del proveedor"}.get(key, FIELDS_ES.get(key, key).lower())
            item.update(kind="review", actor=payload["actor"],
                        title=f'{payload["actor"]} {"corrigió" if changed else "confirmó"} {field_name}',
                        reason=payload["reason"],
                        changes=[{"field": FIELDS_ES.get(key, key), "before": values.get(key), "after": value}])
            values[key] = value
            corrections.append(item)
        elif kind == "alberto_answered":
            verb = {"PAGAR": "aprobó para pago", "NO_PAGAR": "decidió no pagar", "ESCALAR": "pidió información"}[payload["result"]]
            item.update(kind="answer", actor=payload["actor"], title=f'{payload["actor"]} {verb}',
                        reason=payload["reason"], evidence=payload["evidence"])
        elif kind == "human_answer_retracted":
            item.update(kind="withdrawal", actor=payload["retracted_by"],
                        title=f'{payload["retracted_by"]} retiró la respuesta anterior',
                        reason=payload["reason"])
        elif kind == "decision_published":
            decision = versions.get(payload.get("decision_id"))
            if not decision:
                continue
            title = "Primera comprobación" if first_check else "Comprobaciones actualizadas"
            first_check = False
            # The preceding human event already explains this decision.
            if decision.get("human_decision"):
                previous_decision = decision
                continue
            state = {"PAGAR": "Propuesta de pago; aún sin aprobación humana.",
                     "NO_PAGAR": "No se propone el pago.",
                     "ESCALAR": "Pendiente de resolver las dudas indicadas."}[decision["result"]]
            item.update(kind="check", title=title, reason=state + " " + decision_summary(decision)["title"])
            # Ignore implementation fingerprints, never business differences.
            signature = json.dumps({
                "result": decision["result"], "reason": item["reason"],
                "fields": {k: {a: v.get(a) for a in ("value", "status")} for k, v in decision.get("fields", {}).items()},
                "issues": [{k: rule.get(k) for k in ("id", "state", "message", "question", "evidence")}
                           for rule in decision.get("rules", []) if rule["state"] != "PASS"],
                "questions": decision.get("questions", []),
            }, sort_keys=True, ensure_ascii=False)
            before = (previous_decision or {}).get("context", {})
            after = decision.get("context", {})
            causes = [label for key, label in (
                ("code_sha256", "actualización de la aplicación"),
                ("master_id", "actualización del Excel"),
                ("snapshot_id", "nueva consulta contable"),
                ("policy_id", "actualización de reglas"),
                ("extraction_version", "actualización de la lectura"),
                ("as_of", "cambio de fecha de referencia"))
                if previous_decision and before.get(key) != after.get(key)]
            cause = "; ".join(causes) or ("primera comprobación" if previous_decision is None else "recomprobación de los datos registrados")
            item.update(signature=signature, check_runs=[{"date": item["date"], "cause": cause}])
            previous_decision = decision
            if activity and activity[-1]["kind"] == "check" and activity[-1].get("signature") == signature:
                group = activity[-1]
                group["check_runs"].extend(item["check_runs"])
                group["date"] = item["date"]
                group["title"] = f'{len(group["check_runs"])} comprobaciones automáticas · mismo resultado'
                continue
        else:
            continue
        activity.append(item)
    for item in activity:
        item.pop("signature", None)
    return {"activity": list(reversed(activity)), "latest_correction": corrections[-1] if corrections else None}


def human_actions(decision, busy=False):
    if not decision:
        return {"can_pay": False, "reason": "Primero hay que terminar las comprobaciones."}
    protected = payment_blockers(decision)
    no_pay = decision.get("engine_result", decision["result"]) == "NO_PAGAR"
    can_pay = not busy and not protected and not no_pay
    return {"can_pay": can_pay, "reason": "" if can_pay else (
        "Primero hay que terminar las comprobaciones pendientes." if busy else
        "Antes de aprobar, resuelve los datos o comprobaciones pendientes. Puedes corregir una lectura, pedir información o decidir no pagar.")}


def invoice_issue(decision):
    """A concise diagnosis, separate from what the reviewer should do next.

    Uses recorded rule evidence only. Never infers a fault from a question and
    never rewrites the canonical result or hides a human-reviewed discrepancy.
    """
    if not decision:
        return {"title": "Comprobación pendiente", "others": [], "state": "pending", "reviewed": False}
    failed = [rule for rule in decision["rules"] if rule["state"] != "PASS"]
    if failed:
        view = dict(decision, result="ESCALAR", human_decision=None, human_response_stale=False)
        summary = decision_summary(view)
        title, others = summary["title"], summary["others"]
        if decision.get("engine_result", decision["result"]) == "NO_PAGAR":
            paid = next((r for r in failed if r["id"] == "erp_pending"), None)
            duplicate = next((r for r in failed if r["id"] == "duplicate_obligation"), None)
            if paid and (paid["evidence"].get("erp") or {}).get("estado") == "PAGADA":
                title = "El pedido ya consta pagado."
            elif duplicate and duplicate["evidence"].get("state") == "confirmed_copy":
                title = "Copia idéntica de otra factura."
            others = [t for t in [summary["title"], *others] if t != title and t not in (
                "No podemos confirmar que el pedido esté pendiente de pago.",
                "Hay otras facturas que podrían corresponder al mismo pago.")]
        state = "issue"
    else:
        title, others, state = "Sin incidencias detectadas", [], "clear"
    if decision.get("human_response_stale"):
        others = ([title] if failed else []) + others
        title, state = "Una revisión anterior necesita confirmación.", "issue"
    reviewed = bool(decision.get("human_decision") and decision["result"] != "ESCALAR")
    return {"title": title, "others": others, "state": state, "reviewed": reviewed}


def decision_summary(decision):
    """Explain the recorded result without inventing a business fact or changing it."""
    if not decision:
        return None
    if decision.get("human_decision") or decision.get("human_response_stale"):
        return {"title": decision["reason"], "next": "La respuesta y su evidencia se conservan en este expediente.", "others": []}
    if decision["result"] != "ESCALAR":
        return {
            "title": "Las comprobaciones respaldan proponer el pago." if decision["result"] == "PAGAR" else decision["reason"],
            "next": "Es una propuesta: no se ha realizado ningún pago." if decision["result"] == "PAGAR" else "No proponemos un nuevo pago. Puedes consultar el original y dejar una respuesta.",
            "others": [],
        }
    titles = {
        "document_instructions": "La factura contiene una orden sospechosa.",
        "document_coverage": "No hemos podido leer todo el documento con suficiente fiabilidad.",
        "currency": "La moneda no está confirmada.",
        "supplier_identity": "No podemos confirmar quién es el proveedor.",
        "iban_matches_master": "La cuenta bancaria no está confirmada.",
        "order_exists": "No hemos encontrado un pedido contable inequívoco.",
        "order_supplier": "El proveedor de la factura y el del pedido necesitan revisión.",
        "source_identity_conflict": "El Excel y la contabilidad no coinciden en el proveedor.",
        "amount_matches_order": "El importe necesita comprobarse con el pedido.",
        "tax_arithmetic": "El cálculo del IVA necesita revisión.",
        "total_arithmetic": "El total necesita comprobarse con la base y el IVA.",
        "invoice_date": "La fecha de emisión necesita confirmación.",
        "erp_pending": "No podemos confirmar que el pedido esté pendiente de pago.",
        "duplicate_obligation": "Hay otras facturas que podrían corresponder al mismo pago.",
        "historical_order": "El pedido aparece en el archivo de años anteriores.",
    }
    pending = [r for r in decision["rules"] if r["state"] != "PASS"]
    priority = {"document_instructions": 0, "currency": 1, "iban_matches_master": 3}
    pending.sort(key=lambda r: priority.get(r["id"], 2 if r["id"].startswith("field:") else 4))
    reasons = []
    for rule in pending:
        label = titles.get(rule["id"], rule["question"] or rule["message"])
        if rule["id"] == "historical_order" and not rule["evidence"].get("rows"):
            label = "Falta comprobar el pedido con el archivo histórico."
        if rule["id"].startswith("field:"):
            label = "Falta confirmar: " + FIELDS_ES.get(rule["id"][6:], "un dato de la factura").lower() + "."
        if label not in reasons:
            reasons.append(label)
    first = pending[0] if pending else None
    next_step = first["question"] if first else "Revisa las comprobaciones y aporta la información que falta."
    if first and first["id"] == "document_instructions":
        next_step = "No hemos seguido esa orden. Revisa el texto del original y confirma su legitimidad antes de continuar."
    if first and first["id"] == "currency" and decision["fields"]["currency"]["status"] == "MISSING":
        reasons[0] = "La factura no indica la moneda."
        next_step = "Pide al proveedor que confirme la moneda y registra quién la ha confirmado. EUR por norma cuando la cuenta es española y la factura no imprime moneda; cualquier otra moneda o cuenta extranjera requiere confirmación."
    return {"title": reasons[0] if reasons else decision["reason"], "next": next_step, "others": reasons[1:]}

def decorate_dashboard(service, data):
    masters = {b["id"]: service.store.source(b["master_id"]) for b in data["batches"]}
    for item in data["documents"]:
        found = {s["name"] for rows in masters[item["batch_id"]]["suppliers"].values() for s in rows if s["nif"] == item["nif"]}
        item["supplier"] = next(iter(found)) if len(found) == 1 else "Proveedor por confirmar"
    data["documents"].sort(key=lambda d: ({None:0, "ESCALAR":1, "NO_PAGAR":2, "PAGAR":3}.get(d["result"],4),d["file_id"]))
    return data
