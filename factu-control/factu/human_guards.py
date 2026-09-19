"""Shared payment guard, independent of UI and storage."""


def payment_blockers(decision):
    return [r for r in decision["rules"] if r["state"] != "PASS" and
            (r["state"] == "UNKNOWN" or not (
                r["id"] in ("source_identity_conflict", "document_instructions", "historical_order") or
                r["id"].startswith("extra:")))]
