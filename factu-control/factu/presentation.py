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

GENERIC_EXPLANATION = "Comprobación respaldada por los datos registrados."


def _field_value(fields, key):
    entry = (fields or {}).get(key) or {}
    value = entry.get("value")
    if value is None or value == "":
        return None
    return value


def _mask_iban(iban):
    text = str(iban or "").replace(" ", "")
    if len(text) < 8:
        return text or None
    return f"{text[:4]}…{text[-4:]}"


def rule_explanation(rule, fields):
    """Explicación específica en castellano llano para una comprobación.

    Devuelve una frase con los valores reales de la factura. Si falta algún
    dato o algo falla, degrada al texto genérico sin lanzar excepciones.
    """
    try:
        rule_id = rule.get("id") or ""
        state = rule.get("state") or ""
        evidence = rule.get("evidence") or {}
        fields = fields or {}

        if rule_id.startswith("field:"):
            key = rule_id[6:]
            label = FIELDS_ES.get(key, key).lower()
            value = _field_value(fields, key)
            if state == "PASS":
                if value is None:
                    if key == "invoice_number":
                        return "La lectura del número de factura es informativa y no bloquea la decisión."
                    return GENERIC_EXPLANATION
                if key == "iban":
                    masked = _mask_iban(value)
                    if masked:
                        return f"Se leyó la cuenta {masked} en el documento."
                    return GENERIC_EXPLANATION
                if key in ("base", "tax_amount", "total"):
                    return f"Se leyó {label}: {euros(value)} en el documento."
                if key == "tax_rate":
                    return f"Se leyó un tipo de IVA del {value} % en el documento."
                if key == "date":
                    return f"Se leyó la fecha de emisión {value} en el documento."
                return f"Se leyó {label}: {value} en el documento."
            return GENERIC_EXPLANATION

        if rule_id == "document_instructions":
            if state == "PASS":
                return "El texto del documento no contiene órdenes dirigidas al sistema."
            matches = evidence.get("matches") or []
            if matches:
                n = len(matches)
                return (f"El documento contiene {n} fragmentos sospechosos que intentan dar instrucciones al sistema."
                        if n != 1 else "El documento contiene un fragmento sospechoso que intenta dar instrucciones al sistema.")
            return GENERIC_EXPLANATION

        if rule_id == "document_coverage":
            if state == "PASS":
                return "Se leyeron todas las páginas del documento con la fiabilidad exigida."
            warnings = evidence.get("warnings") or []
            if warnings:
                n = len(warnings)
                return (f"Quedan {n} avisos de cobertura pendientes de revisar en el documento."
                        if n != 1 else "Queda un aviso de cobertura pendiente de revisar en el documento.")
            return GENERIC_EXPLANATION

        if rule_id == "supplier_identity":
            nif = evidence.get("nif") or _field_value(fields, "supplier_nif")
            rows = evidence.get("rows") or []
            if state == "PASS":
                name = None
                if rows:
                    name = rows[0].get("name") or rows[0].get("id")
                if nif and name:
                    return f"El NIF {nif} identifica de forma única al proveedor {name} en el maestro."
                if nif:
                    return f"El NIF {nif} identifica de forma única al proveedor en el maestro."
                return GENERIC_EXPLANATION
            return GENERIC_EXPLANATION

        if rule_id == "iban_matches_master":
            invoice_iban = evidence.get("invoice_iban") or _field_value(fields, "iban")
            master_iban = evidence.get("master_iban")
            if state == "PASS":
                masked = _mask_iban(invoice_iban)
                if masked:
                    return f"La cuenta de la factura ({masked}) coincide con la registrada en el maestro de proveedores."
                return GENERIC_EXPLANATION
            if invoice_iban and master_iban:
                return f"La cuenta de la factura ({_mask_iban(invoice_iban)}) no coincide con la del maestro ({_mask_iban(master_iban)})."
            return GENERIC_EXPLANATION

        if rule_id == "order_exists":
            order = evidence.get("order") or _field_value(fields, "order")
            erp = evidence.get("erp") or {}
            if state == "PASS":
                estado = erp.get("estado")
                if order and estado:
                    return f"El pedido {order} figura en la contabilidad con estado {estado}."
                if order:
                    return f"El pedido {order} figura en la contabilidad."
                return GENERIC_EXPLANATION
            if order:
                return f"No se ha encontrado un asiento inequívoco para el pedido {order} en la contabilidad."
            return GENERIC_EXPLANATION

        if rule_id == "order_supplier":
            supplier = evidence.get("supplier") or {}
            erp = evidence.get("erp") or {}
            name = supplier.get("name") if isinstance(supplier, dict) else None
            supplier_id = supplier.get("id") if isinstance(supplier, dict) else None
            order = erp.get("pedido") if isinstance(erp, dict) else None
            if state == "PASS":
                if order and name:
                    return f"El proveedor del pedido {order} en la contabilidad ({name}) coincide con el de la factura."
                if name:
                    return f"El proveedor del pedido en la contabilidad ({name}) coincide con el de la factura."
                if supplier_id:
                    return f"El proveedor de la factura ({supplier_id}) coincide con el del pedido en la contabilidad."
                return GENERIC_EXPLANATION
            return GENERIC_EXPLANATION

        if rule_id == "source_identity_conflict":
            if state == "PASS":
                return "El Excel y la contabilidad indican el mismo proveedor para este pedido."
            return GENERIC_EXPLANATION

        if rule_id == "amount_matches_order":
            invoice_total = evidence.get("invoice") or _field_value(fields, "total")
            erp_total = evidence.get("erp")
            currency = evidence.get("currency") or _field_value(fields, "currency") or "EUR"
            tol = evidence.get("tolerance") or "0.01"
            order = _field_value(fields, "order")
            if state == "PASS":
                if invoice_total is not None and order:
                    return f"El total de la factura ({euros(invoice_total)} {currency}) coincide con el importe del pedido {order} registrado en la contabilidad (tolerancia {tol} {currency})."
                if invoice_total is not None:
                    return f"El total de la factura ({euros(invoice_total)} {currency}) coincide con el importe del pedido registrado en la contabilidad (tolerancia {tol} {currency})."
                return GENERIC_EXPLANATION
            if invoice_total is not None and erp_total is not None:
                return f"El total de la factura ({euros(invoice_total)} {currency}) no coincide con el importe del pedido en la contabilidad ({euros(erp_total)} {currency})."
            return GENERIC_EXPLANATION

        if rule_id == "tax_arithmetic":
            base = evidence.get("base") or _field_value(fields, "base")
            rate = evidence.get("rate") or _field_value(fields, "tax_rate")
            tax = evidence.get("tax") or _field_value(fields, "tax_amount")
            if state == "PASS" and base is not None and rate is not None and tax is not None:
                return f"La cuota de IVA ({euros(tax)}) corresponde a la base ({euros(base)}) al tipo del {rate} %."
            if state != "PASS" and base is not None and rate is not None and tax is not None:
                return f"La cuota leída ({euros(tax)}) no cuadra con la base ({euros(base)}) al tipo del {rate} %."
            return GENERIC_EXPLANATION

        if rule_id == "total_arithmetic":
            base = evidence.get("base") or _field_value(fields, "base")
            tax = evidence.get("tax") or _field_value(fields, "tax_amount")
            total = evidence.get("total") or _field_value(fields, "total")
            if state == "PASS" and base is not None and tax is not None and total is not None:
                return f"El total ({euros(total)}) es la suma de base ({euros(base)}) e IVA ({euros(tax)})."
            if state != "PASS" and base is not None and tax is not None and total is not None:
                return f"El total leído ({euros(total)}) no es la suma de base ({euros(base)}) e IVA ({euros(tax)})."
            return GENERIC_EXPLANATION

        if rule_id == "invoice_date":
            invoice_dt = evidence.get("invoice") or _field_value(fields, "date")
            as_of = evidence.get("as_of")
            if state == "PASS" and invoice_dt:
                return f"La fecha de emisión ({invoice_dt}) es válida y no es futura."
            if state != "PASS" and invoice_dt and as_of:
                return f"La fecha de emisión ({invoice_dt}) no es válida frente a la fecha de referencia ({as_of})."
            return GENERIC_EXPLANATION

        if rule_id == "currency":
            currency = _field_value(fields, "currency")
            allowed = evidence.get("allowed") or []
            if state == "PASS" and currency:
                return f"La moneda de la factura ({currency}) está permitida por la norma."
            if state != "PASS" and currency and allowed:
                return f"La moneda leída ({currency}) no está entre las permitidas por la norma ({', '.join(allowed)})."
            return GENERIC_EXPLANATION

        if rule_id == "erp_pending":
            erp = evidence.get("erp") or {}
            order = erp.get("pedido") or _field_value(fields, "order")
            estado = erp.get("estado")
            if state == "PASS" and order:
                return f"El pedido {order} consta como PENDIENTE en la contabilidad: aún no se ha pagado."
            if state != "PASS" and order and estado:
                return f"El pedido {order} consta como {estado} en la contabilidad."
            return GENERIC_EXPLANATION

        if rule_id == "duplicate_obligation":
            related = rule.get("evidence", {}).get("related") or []
            dstate = rule.get("evidence", {}).get("state") or ""
            if state == "PASS":
                return "No hemos encontrado otras facturas con el mismo pedido en este lote."
            if related:
                n = len(related)
                if dstate == "confirmed_copy":
                    return (f"Copia idéntica: {n} facturas previas con el mismo pedido."
                            if n != 1 else "Copia idéntica: una factura previa con el mismo pedido.")
                return (f"Hay {n} facturas que comparten pedido con esta."
                        if n != 1 else "Hay otra factura que comparte pedido con esta.")
            return GENERIC_EXPLANATION

        if rule_id == "historical_order":
            rows = evidence.get("rows") or []
            loaded = evidence.get("loaded")
            order = evidence.get("order") or _field_value(fields, "order")
            if state == "PASS":
                if loaded and order:
                    return f"El pedido {order} no aparece en el archivo histórico disponible."
                return GENERIC_EXPLANATION
            if rows and order:
                return f"El pedido {order} aparece {len(rows)} vez/veces en el archivo histórico."
            return GENERIC_EXPLANATION

        if rule_id == "order_read_by_model":
            erp = evidence.get("erp") or {}
            order = _field_value(fields, "order")
            if state == "PASS":
                if evidence.get("solo_modelo") is False:
                    return "El número de pedido se leyó del texto original del documento."
                if order:
                    return f"El pedido {order} se aceptó porque la contabilidad no lo da por pagado."
                return GENERIC_EXPLANATION
            return GENERIC_EXPLANATION

        return GENERIC_EXPLANATION
    except Exception:
        return GENERIC_EXPLANATION


def decorate_dashboard(service, data):
    masters = {b["id"]: service.store.source(b["master_id"]) for b in data["batches"]}
    for item in data["documents"]:
        found = {s["name"] for rows in masters[item["batch_id"]]["suppliers"].values() for s in rows if s["nif"] == item["nif"]}
        item["supplier"] = next(iter(found)) if len(found) == 1 else "Proveedor por confirmar"
    data["documents"].sort(key=lambda d: ({None:0, "ESCALAR":1, "NO_PAGAR":2, "PAGAR":3}.get(d["result"],4),d["file_id"]))
    return data
