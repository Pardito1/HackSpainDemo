"""Shared payment guard, independent of UI and storage."""

# Discrepancias de negocio que una persona puede revisar y asumir de forma
# explícita (con su justificación) para aprobar el pago. El resto -cuenta,
# importe, duplicados, pagos previos- nunca se pasa por alto: hay que
# corregir antes el dato leído.
OVERRIDABLE_RULES = ("source_identity_conflict", "document_instructions", "historical_order", "currency")


def payment_blockers(decision):
    return [r for r in decision["rules"] if r["state"] != "PASS" and
            not (r["id"] in OVERRIDABLE_RULES or r["id"].startswith("extra:"))]
