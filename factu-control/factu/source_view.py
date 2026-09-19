"""Business presentation derived from recorded sources, not fabricated freshness."""
from collections import defaultdict

from .historical import SHEET
from .utils import identifier


def impact_counts(plan):
    affected = plan["affected"]
    unchanged = sum(d["before"] == d["after"] for d in affected)
    to_review = sum(d["before"] != "ESCALAR" and d["after"] == "ESCALAR" for d in affected)
    return {"affected": len(affected), "unchanged": unchanged, "to_review": to_review,
            "other_changes": len(affected) - unchanged - to_review, "reused": len(plan["reused"])}


def source_view(service, data, focused_change=None):
    batch, master, snapshot, policy = (data[k] for k in ("batch", "master", "snapshot", "policy"))
    by_nif = defaultdict(set)
    for group in master["suppliers"].values():
        for supplier in group:
            by_nif[supplier["nif"]].add((supplier["id"], supplier["iban"]))
    identity_conflicts = sum(len(v) > 1 for v in by_nif.values())
    conflicting_orders = set()
    for row in (snapshot or {}).get("rows", []):
        key = identifier(row["pedido"])
        for order in master["orders"].get(key, []):
            if order["supplier_id"] != row["proveedor"] or (order["nif"] and row["nif"] and identifier(order["nif"]) != identifier(row["nif"])):
                conflicting_orders.add(key)
    history = master.get("historical", {})
    history_pending = SHEET in master.get("sheets", []) and not history
    dates = {}
    for kind, key in (("master", "master_id"), ("erp", "snapshot_id"), ("policy", "policy_id")):
        row = service.store.one("SELECT created FROM sources WHERE id=?", (batch[key],)) if batch[key] else None
        dates[kind] = row["created"] if row else None
    changes = [dict(row, impact=impact_counts(row["plan"])) for row in data["changes"]]
    selected = next((r for r in changes if r["id"] == focused_change), None)
    if not focused_change:
        selected = next((r for r in changes if r["status"] == "PREVIEW"), None)
    rules = [
        "Identificar al proveedor y comprobar su cuenta bancaria.",
        "Contrastar el pedido, su importe y su estado de pago con la contabilidad.",
        f"Comprobar base, IVA y total con una tolerancia de {policy['tolerance_eur']}.",
        "Comprobar la fecha de emisión y confirmar la moneda: " + ", ".join(policy["allowed_currencies"]) + ".",
        "Buscar copias, pedidos compartidos y coincidencias en el histórico disponible.",
        "Pedir revisión humana si faltan datos o las fuentes se contradicen. No ejecutar pagos.",
    ]
    rules.extend(r["question"] for r in policy["extra_rules"])
    return {"source_dates": dates, "identity_conflicts": identity_conflicts,
            "conflicting_orders": len(conflicting_orders), "history_pending": history_pending,
            "historical_count": sum(len(rows) for rows in history.get("orders", {}).values()),
            "history_available": history.get("available", False),
            "historical_warnings": history.get("warnings", []),
            "current_change": selected, "change_history": changes, "human_rules": rules,
            "master_has_issues": bool(identity_conflicts or conflicting_orders or history_pending or history.get("warnings")),
            "erp_complete": bool(snapshot and snapshot.get("complete"))}
