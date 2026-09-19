from __future__ import annotations

import copy
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .extract import FIELDS
from .utils import identifier, invoice_date, money
from .presentation import FIELDS_ES
from .historical import history_dependency


# Lote 2 puede identificar otras divisas impresas. Esto no permite todavía
# conciliarlas contra un ERP sin divisa: esa conversión se bloquea de forma
# explícita en `amount_matches_order`.
SUPPORTED_CURRENCIES = ("EUR", "USD", "GBP", "CHF", "JPY", "BRL", "MXN")


def _erp_alias(row, names, normalizer):
    """Read one logical ERP field without silently choosing between aliases.

    The HTTP bridge exposes ``proveedor``, ``importe`` and ``fecha`` whereas
    the Lote 2 export uses ``*_id``, ``*_esperado`` and
    ``fecha_registro``.  A source that happens to contain both spellings must
    agree; otherwise it is not a reliable history to use for a payment
    decision.
    """
    values = []
    for name in names:
        raw = row.get(name)
        if raw is None or not str(raw).strip():
            continue
        try:
            values.append((name, normalizer(raw)))
        except (TypeError, ValueError, ArithmeticError):
            return None, "malformed_" + name
    if not values:
        return None, "missing_" + names[0]
    if len({value for _, value in values}) != 1:
        return None, "conflicting_" + "_".join(names)
    return values[0][1], None


def resolve_erp_history(rows):
    """Resolve a same-order ERP history only when its latest state is safe.

    This deliberately keeps *every* source row in ``records``.  A later ERP
    record can supersede an earlier status (for example PENDIENTE -> PAGADA),
    but only if all records agree on provider, NIF and amount and exactly one
    valid latest registration date exists.  Any data quality ambiguity returns
    no effective ERP row, which makes the business decision ``ESCALAR``.
    """
    records = list(rows or [])
    result = {"records": records, "state": "MISSING", "reason": "no_records"}
    if not records:
        return result

    normalized = []
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            result.update(state="AMBIGUOUS", reason="invalid_record")
            return result
        order, error = _erp_alias(row, ("pedido",), identifier)
        if error:
            result.update(state="AMBIGUOUS", reason=error, record_index=index)
            return result
        provider, error = _erp_alias(row, ("proveedor", "proveedor_id"), identifier)
        if error:
            result.update(state="AMBIGUOUS", reason=error, record_index=index)
            return result
        nif, error = _erp_alias(row, ("nif",), identifier)
        if error:
            result.update(state="AMBIGUOUS", reason=error, record_index=index)
            return result
        amount, error = _erp_alias(row, ("importe", "importe_esperado"), money)
        if error:
            result.update(state="AMBIGUOUS", reason=error, record_index=index)
            return result

        date_values = []
        for name in ("fecha_registro", "fecha"):
            raw = row.get(name)
            if raw is None or not str(raw).strip():
                continue
            try:
                date_values.append((name, invoice_date(raw)))
            except (TypeError, ValueError):
                result.update(
                    state="AMBIGUOUS",
                    reason="malformed_" + name,
                    record_index=index,
                )
                return result
        if not date_values:
            result.update(state="AMBIGUOUS", reason="missing_date", record_index=index)
            return result
        if len({value for _, value in date_values}) != 1:
            result.update(state="AMBIGUOUS", reason="conflicting_date", record_index=index)
            return result

        state = identifier(row.get("estado"))
        if state not in {"PENDIENTE", "PAGADA"}:
            result.update(state="AMBIGUOUS", reason="ambiguous_state", record_index=index)
            return result
        normalized.append(
            {
                "index": index,
                "raw": row,
                "order": order,
                "provider": provider,
                "nif": nif,
                "amount": amount,
                "date": date_values[0][1],
                "state": state,
            }
        )

    # Do not merge rows belonging to different obligations, even if a caller
    # accidentally passed a broader set than one order.
    signatures = {(r["order"], r["provider"], r["nif"], r["amount"]) for r in normalized}
    if len(signatures) != 1:
        result.update(state="AMBIGUOUS", reason="conflicting_identity_or_amount")
        return result

    latest_date = max(r["date"] for r in normalized)
    latest = [r for r in normalized if r["date"] == latest_date]
    if len(latest) != 1:
        result.update(
            state="AMBIGUOUS",
            reason="equal_latest_dates",
            latest_date=latest_date,
            latest_indices=[r["index"] for r in latest],
        )
        return result

    chosen = latest[0]
    # Consumers receive the bridge's canonical field names irrespective of
    # whether the source row originated in XML or the official CSV export.
    erp = dict(chosen["raw"])
    erp.update(
        {
            "pedido": chosen["order"],
            "proveedor": chosen["provider"],
            "nif": chosen["nif"],
            "importe": str(chosen["amount"]),
            "fecha": chosen["date"],
            "estado": chosen["state"],
        }
    )
    result.update(
        state="RESOLVED",
        reason="unique_latest_consistent_record",
        latest_date=latest_date,
        selected_index=chosen["index"],
        selected_record=chosen["raw"],
        erp=erp,
    )
    return result


def validate_policy(policy):
    if not isinstance(policy, dict):
        raise ValueError("La política debe ser un objeto JSON, no una lista ni un valor vacío")
    allowed = {
        "version",
        "source",
        "tolerance_eur",
        "identity_conflict",
        "iban_checksum_required",
        "reject_confirmed_paid",
        "allowed_currencies",
        "default_currency",
        "extra_rules",
        "approved_by",
        "approved_at",
    }
    if set(policy) - allowed:
        raise ValueError(
            "Campos de política no soportados: "
            + ", ".join(sorted(set(policy) - allowed))
        )
    if (
        not isinstance(policy.get("version"), str) or not policy["version"].strip()
        or not isinstance(policy.get("source"), str) or not policy["source"].strip()
        or not 0 <= money(policy.get("tolerance_eur", "-1")) <= 1
    ):
        raise ValueError("Versión, fuente o tolerancia inválida")
    if (
        policy.get("identity_conflict") != "ESCALAR"
        or policy.get("iban_checksum_required") is not False
        or policy.get("reject_confirmed_paid") is not True
    ):
        raise ValueError(
            "Este motor conserva las protecciones v3; cambiar sus semánticas requiere nuevo código y tests"
        )
    if (
        not isinstance(policy.get("allowed_currencies"), list)
        or not policy["allowed_currencies"]
        or any(
            not isinstance(c, str) or c not in SUPPORTED_CURRENCIES
            for c in policy["allowed_currencies"]
        )
    ):
        raise ValueError("Faltan monedas permitidas")
    if "default_currency" in policy:
        default = policy["default_currency"]
        if (
            not isinstance(default, dict)
            or set(default) != {"code", "iban_countries"}
            or not isinstance(default["code"], str)
            or not re.fullmatch(r"[A-Z]{3}", default["code"])
            or not isinstance(default["iban_countries"], list)
            or not default["iban_countries"]
            or any(
                not isinstance(c, str) or not re.fullmatch(r"[A-Z]{2}", c)
                for c in default["iban_countries"]
            )
        ):
            raise ValueError(
                'default_currency debe tener la forma {"code": "<ISO3>", "iban_countries": ["ES", ...]}'
            )
    if not isinstance(policy.get("extra_rules"), list):
        raise ValueError("extra_rules debe ser una lista")
    seen = set()
    for rule in policy["extra_rules"]:
        if (
            not isinstance(rule, dict)
            or set(rule) != {"id", "field", "op", "value", "question"}
            or any(not isinstance(rule[k], str) or not rule[k].strip() for k in ("id", "field", "op", "question"))
            or not isinstance(rule["value"], (str, int, float)) or isinstance(rule["value"], bool)
            or rule["id"] in seen
            or rule["field"] not in (*FIELDS, "currency")
            or rule["op"] not in ("eq", "ne", "lte", "gte")
        ):
            raise ValueError("Regla adicional no soportada")
        if rule["op"] in ("lte", "gte"):
            money(rule["value"])
        seen.add(rule["id"])
    return policy


def apply_reviews(extraction, reviews):
    effective = copy.deepcopy(extraction)
    for review in reviews:
        for field, value in review["corrections"].items():
            effective["fields"][field] = {
                "value": value,
                "status": "OK",
                "evidence": [
                    {
                        "method": "human",
                        "review_id": review["id"],
                        "actor": review["actor"],
                        "reason": review["reason"],
                        "created": review["created"],
                        "value": value,
                    }
                ],
                "original": extraction["fields"].get(field),
            }
    return effective


def evaluate(extraction, master, snapshot, policy, as_of, duplicate=None):
    validate_policy(policy)
    date.fromisoformat(as_of)
    # Copia: la decisión puede anotar la moneda inferida por la norma sin
    # tocar nunca la extracción persistida.
    fields = copy.deepcopy(extraction["fields"])
    rules = []

    def check(code, passed, message, question="", evidence=None):
        state = "UNKNOWN" if passed is None else "PASS" if passed else "FAIL"
        rules.append(
            {
                "id": code,
                "state": state,
                "message": message,
                "question": question if state != "PASS" else "",
                "evidence": evidence or {},
            }
        )
        return passed is True

    def val(field):
        fact = fields.get(field, {})
        return fact.get("value") if fact.get("status") == "OK" else None

    for field in FIELDS:
        # El numero de factura no interviene en ninguna norma: su lectura es
        # informativa y nunca bloquea la decision (una etiqueta o un OCR sucio
        # no deben convertir una factura que cuadra en ESCALAR).
        informativo = field == "invoice_number"
        check(
            "field:" + field,
            True if informativo else val(field) is not None,
            f"Lectura: {FIELDS_ES.get(field, field)}" + (" (informativo)" if informativo else ""),
            f"Confirma {FIELDS_ES.get(field, field).lower()} en el documento original.",
            {"field": field, "candidates": fields.get(field, {}).get("evidence", []),
             "status": fields.get(field, {}).get("status"), "blocking": not informativo},
        )
    complete_pages = not any(
        w["code"] in ("OCR_UNAVAILABLE", "OCR_DISABLED", "OCR_EMPTY")
        for w in extraction.get("warnings", [])
    )
    check("document_instructions", not extraction.get("untrusted_instructions"),
          "Texto que intenta dar instrucciones al sistema",
          "Revisa el texto señalado y confirma su legitimidad antes de resolver esta factura.",
          {"matches": extraction.get("untrusted_instructions", [])})
    check(
        "document_coverage",
        complete_pages,
        "Cobertura de páginas",
        "Revisa las páginas pendientes de OCR.",
        {"warnings": extraction.get("warnings", [])},
    )
    check(
        "document_annotations",
        not extraction.get("annotation_risks"),
        "Sin tachones o anotaciones que cambien el dato",
        "Revisa el documento original: hay una anotación o corrección que puede alterar los datos impresos.",
        {"risks": extraction.get("annotation_risks", [])},
    )
    nif, iban, order = val("supplier_nif"), val("iban"), val("order")
    found = [
        s
        for rows in master["suppliers"].values()
        for s in rows
        if nif and s["nif"] == identifier(nif)
    ]
    signatures = {(s["id"], s["nif"], s["iban"]) for s in found}
    supplier = found[0] if len(signatures) == 1 else None
    check(
        "supplier_identity",
        bool(supplier) if nif else None,
        "Identidad única en el maestro",
        "Confirma el NIF y el registro vigente del proveedor.",
        {"nif": nif, "rows": found},
    )
    check(
        "iban_matches_master",
        identifier(iban) == supplier["iban"] if iban and supplier else None,
        "IBAN de factura frente a maestro",
        "Aporta la cuenta autorizada y la evidencia del dato correcto.",
        {
            "invoice_iban": iban,
            "master_iban": supplier["iban"] if supplier else None,
            "master_sources": [s["source"] for s in found],
        },
    )
    rows = (
        [
            r
            for r in snapshot.get("rows", [])
            if identifier(r["pedido"]) == identifier(order)
        ]
        if order and snapshot
        else []
    )
    erp_history = resolve_erp_history(rows)
    erp = erp_history.get("erp")
    check(
        "erp_history",
        erp_history["state"] == "RESOLVED"
        if order and snapshot and snapshot.get("complete")
        else None,
        "Historial ERP consistente con última fecha única",
        "El ERP contiene varios asientos o fechas ambiguas para este pedido; confirma el estado contable vigente.",
        erp_history,
    )
    check(
        "order_exists",
        bool(erp) if order and snapshot and snapshot.get("complete") else None,
        "Pedido y estado vigente en snapshot ERP completo",
        "Confirma el pedido y su asiento contable.",
        {"order": order, **erp_history},
    )
    expected = master["orders"].get(identifier(order), []) if order else []
    identity_ok = bool(
        supplier
        and erp
        and erp["proveedor"] == supplier["id"]
        and (not erp["nif"] or identifier(erp["nif"]) == supplier["nif"])
    )
    check(
        "order_supplier",
        identity_ok if erp and supplier else None,
        "Proveedor del pedido frente a factura",
        "Aclara la relación entre proveedor y pedido.",
        {"supplier": supplier, "erp": erp},
    )
    excel_ok = bool(erp and supplier) and all(
        o["supplier_id"] == erp["proveedor"]
        and (not o["nif"] or identifier(o["nif"]) == supplier["nif"])
        for o in expected
    )
    check(
        "source_identity_conflict",
        excel_ok if erp else None,
        "Coherencia de identidad Excel / ERP",
        "Confirma qué registro es correcto ante la contradicción de identidad.",
        {"excel": expected, "erp": erp},
    )
    # La moneda se resuelve antes que los importes: `amount_matches_order` solo
    # compara contra el ERP si la divisa es la del ERP, y la norma puede
    # inferirla del país del IBAN cuando la factura no imprime ninguna.
    printed = val("currency")
    currency_ok = printed in policy["allowed_currencies"] if printed else None
    currency_question = "Confirma la moneda y el tratamiento de conversión."
    if printed and currency_ok is False:
        currency_question = (
            f"Moneda {printed} no prevista en la norma: "
            "confirma tipo de cambio y fecha de conversión."
        )
    default = policy.get("default_currency")
    if (
        printed is None
        and fields.get("currency", {}).get("status") == "MISSING"
        and not fields.get("currency", {}).get("evidence")
        and default
        and iban
        and identifier(iban)[:2] in default["iban_countries"]
    ):
        iban_line = next(
            (
                c.get("source_text")
                for c in fields.get("iban", {}).get("evidence", [])
                if c.get("value") == iban
            ),
            None,
        )
        fields["currency"] = {
            "value": default["code"],
            "status": "OK",
            "evidence": [
                {
                    "method": "policy",
                    "value": default["code"],
                    "raw_value": None,
                    "source_text": iban_line,
                    "transformations": [
                        f"default_currency:iban_country={identifier(iban)[:2]}"
                    ],
                    "policy_version": policy["version"],
                }
            ],
            "inferred": True,
        }
        currency_ok = True
    tol = money(policy["tolerance_eur"])
    total, base, tax, rate = (
        val(f) for f in ("total", "base", "tax_amount", "tax_rate")
    )

    def numeric(values, comparison):
        if any(v is None for v in values):
            return None
        try:
            return comparison(*[money(v) for v in values])
        except (ValueError, ArithmeticError):
            return None

    # El ERP legado no declara divisa ni tipo de cambio. Comparar un total en
    # USD, JPY, BRL, etc. como si fuese EUR sería una falsa conciliación. Una
    # política futura deberá aportar importe nativo, FX, fecha y fuente.
    invoice_currency = val("currency")
    amount_comparable = invoice_currency == "EUR"
    check(
        "amount_matches_order",
        numeric(
            [total, erp["importe"] if erp else None], lambda a, b: abs(a - b) <= tol
        ) if amount_comparable else None,
        "Total frente al importe ERP",
        (
            "Aclara el importe del pedido o aporta factura corregida."
            if amount_comparable
            else "No hay una conversión de moneda trazable frente al ERP; confirma divisa, tipo de cambio y fuente autorizada."
        ),
        {
            "invoice": total,
            "erp": erp["importe"] if erp else None,
            "currency": invoice_currency,
            "comparable": amount_comparable,
            "tolerance": str(tol),
        },
    )
    check(
        "tax_arithmetic",
        numeric(
            [base, rate, tax],
            lambda b, r, t: abs(
                (b * r / 100).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) - t
            )
            <= tol,
        ),
        "IVA = base × tipo",
        "Revisa base, tipo y cuota de IVA.",
        {"base": base, "rate": rate, "tax": tax, "tolerance": str(tol)},
    )
    check(
        "total_arithmetic",
        numeric([base, tax, total], lambda b, t, a: abs(b + t - a) <= tol),
        "Total = base + IVA",
        "Aclara el descuadre entre base, IVA y total.",
        {"base": base, "tax": tax, "total": total, "tolerance": str(tol)},
    )
    try:
        valid_date = (
            date.fromisoformat(val("date")) <= date.fromisoformat(as_of)
            if val("date")
            else None
        )
    except (ValueError, TypeError):
        valid_date = False
    check(
        "invoice_date",
        valid_date,
        "Fecha válida y no futura",
        "Confirma la fecha de emisión.",
        {"invoice": val("date"), "as_of": as_of},
    )
    check(
        "currency",
        currency_ok,
        "Moneda permitida",
        currency_question,
        {"currency": fields.get("currency"), "allowed": policy["allowed_currencies"]},
    )
    check(
        "erp_pending",
        erp["estado"] == "PENDIENTE" if erp else None,
        "Estado contable PENDIENTE",
        "Revisa el estado contable.",
        {"erp": erp},
    )
    duplicate = duplicate or {"state": "none", "related": []}
    check(
        "duplicate_obligation",
        duplicate["state"] == "none",
        "Obligación no duplicada",
        "Revisa las facturas que comparten pedido.",
        duplicate,
    )
    historical = history_dependency(master, order)
    check(
        "historical_order",
        not historical["rows"] if historical["loaded"] and order else None,
        "Pedido contrastado con el archivo histórico disponible",
        "Este pedido aparece en el archivo antiguo. Confirma si es una obligación distinta y aporta evidencia de su estado de pago."
        if historical["rows"] else "Vuelve a cargar el Excel para comprobar el histórico o confirma el número de pedido.",
        {**historical, "order": order,
         "limit": "Archivo parcial: no contiene proveedor, número de factura ni estado de pago. La ausencia de coincidencia no descarta otros antecedentes."},
    )
    for extra in policy["extra_rules"]:
        current = val(extra["field"])
        passed = None
        if current is not None:
            if extra["op"] in ("eq", "ne"):
                passed = (current == str(extra["value"])) == (extra["op"] == "eq")
            else:
                passed = numeric(
                    [current, extra["value"]],
                    lambda a, b: a <= b if extra["op"] == "lte" else a >= b,
                )
        check(
            "extra:" + extra["id"],
            passed,
            extra["id"],
            extra["question"],
            {"actual": current, "expected": extra["value"], "op": extra["op"]},
        )
    soporte_order = [
        c
        for c in fields.get("order", {}).get("evidence", [])
        if val("order") is not None and c.get("value") == val("order")
    ]
    assisted_methods = {"modelo", "rapidocr-lote2"}
    order_solo_modelo = bool(soporte_order) and all(
        c.get("method") in assisted_methods for c in soporte_order
    )
    check(
        "order_read_by_model",
        not (order_solo_modelo and erp and erp["estado"] == "PAGADA"),
        "Ningún rechazo depende solo de una lectura asistida",
        "El número de pedido lo leyó un OCR o modelo y el ERP lo da por pagado: "
        "confirma el pedido en el original antes de rechazar el pago",
        {"solo_modelo": order_solo_modelo, "erp": erp},
    )
    confirmed_paid = (
        identity_ok
        and snapshot.get("complete") is True
        and excel_ok
        and erp
        and erp["estado"] == "PAGADA"
        and val("order") is not None
        and not order_solo_modelo
    )
    confirmed_copy = duplicate["state"] == "confirmed_copy"
    # A confirmed byte-for-byte copy is normally safe to reject, but it must
    # not conceal contradictory ERP records for the very same order.
    erp_history_ambiguous = bool(rows) and erp_history["state"] != "RESOLVED"
    result = (
        "NO_PAGAR"
        if (confirmed_paid or confirmed_copy)
        and not erp_history_ambiguous
        and not extraction.get("untrusted_instructions")
        else "PAGAR" if all(r["state"] == "PASS" for r in rules) else "ESCALAR"
    )
    reason = (
        "Pedido ya pagado en ERP"
        if confirmed_paid and result == "NO_PAGAR"
        else (
            "Copia idéntica; conservar una sola obligación"
            if confirmed_copy and result == "NO_PAGAR"
            else (
                "Todos los controles superados"
                if result == "PAGAR"
                else "Se necesita evidencia o resolución humana"
            )
        )
    )
    return {
        "result": result,
        "reason": reason,
        "rules": rules,
        "fields": fields,
        "policy_version": policy["version"],
        "as_of": as_of,
        "questions": (
            [r["question"] for r in rules if r["question"]]
            if result == "ESCALAR"
            else []
        ),
        "diagnostics": {
            "untrusted_instructions": extraction.get("untrusted_instructions", []),
            "iban_checksum_is_blocking": False,
        },
    }
