from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .extract import FIELDS
from .utils import identifier, money
from .presentation import FIELDS_ES


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
        or any(not isinstance(c, str) or c not in ("EUR", "USD", "GBP", "CHF") for c in policy["allowed_currencies"])
    ):
        raise ValueError("Faltan monedas permitidas")
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
    fields = extraction["fields"]
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
    erp = rows[0] if len(rows) == 1 else None
    check(
        "order_exists",
        bool(erp) if order and snapshot and snapshot.get("complete") else None,
        "Pedido único en snapshot ERP completo",
        "Confirma el pedido y su asiento contable.",
        {"order": order, "records": rows},
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

    check(
        "amount_matches_order",
        numeric(
            [total, erp["importe"] if erp else None], lambda a, b: abs(a - b) <= tol
        ),
        "Total frente al importe ERP",
        "Aclara el importe del pedido o aporta factura corregida.",
        {
            "invoice": total,
            "erp": erp["importe"] if erp else None,
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
        val("currency") in policy["allowed_currencies"] if val("currency") else None,
        "Moneda permitida",
        "Confirma la moneda y el tratamiento de conversión.",
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
    confirmed_paid = (
        identity_ok
        and snapshot.get("complete") is True
        and excel_ok
        and erp
        and erp["estado"] == "PAGADA"
        and val("order") is not None
    )
    confirmed_copy = duplicate["state"] == "confirmed_copy"
    result = (
        "NO_PAGAR"
        if (confirmed_paid or confirmed_copy) and not extraction.get("untrusted_instructions")
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
