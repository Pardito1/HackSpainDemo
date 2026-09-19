from factu.presentation import rule_explanation, GENERIC_EXPLANATION


FIELDS = {
    "invoice_number": {"status": "OK", "value": "F26-3011"},
    "supplier_nif": {"status": "OK", "value": "B12345678"},
    "iban": {"status": "OK", "value": "ES2702390806667122334455"},
    "order": {"status": "OK", "value": "PO-2026-0071"},
    "date": {"status": "OK", "value": "2026-05-24"},
    "base": {"status": "OK", "value": "786,69"},
    "tax_rate": {"status": "OK", "value": "21"},
    "tax_amount": {"status": "OK", "value": "165,20"},
    "total": {"status": "OK", "value": "951,89"},
    "currency": {"status": "OK", "value": "EUR"},
}


def test_field_iban_pass_masks_value():
    rule = {"id": "field:iban", "state": "PASS", "evidence": {}, "question": "", "message": ""}
    text = rule_explanation(rule, FIELDS)
    assert "ES27" in text and "4455" in text
    assert "ES2702390806667122334455" not in text


def test_field_total_pass_uses_euros_format():
    rule = {"id": "field:total", "state": "PASS", "evidence": {}, "question": "", "message": ""}
    text = rule_explanation(rule, FIELDS)
    assert "951,89" in text


def test_iban_matches_master_pass_shows_masked_iban():
    rule = {
        "id": "iban_matches_master",
        "state": "PASS",
        "evidence": {"invoice_iban": "ES2702390806667122334455", "master_iban": "ES2702390806667122334455"},
        "question": "", "message": "",
    }
    text = rule_explanation(rule, FIELDS)
    assert "coincide" in text
    assert "ES27" in text and "4455" in text
    assert "ES2702390806667122334455" not in text


def test_tax_arithmetic_pass_mentions_base_rate_and_tax():
    rule = {
        "id": "tax_arithmetic",
        "state": "PASS",
        "evidence": {"base": "786,69", "rate": "21", "tax": "165,20", "tolerance": "0.01"},
        "question": "", "message": "",
    }
    text = rule_explanation(rule, FIELDS)
    assert "165,20" in text and "786,69" in text and "21" in text


def test_total_arithmetic_pass_mentions_sum_components():
    rule = {
        "id": "total_arithmetic",
        "state": "PASS",
        "evidence": {"base": "786,69", "tax": "165,20", "total": "951,89", "tolerance": "0.01"},
        "question": "", "message": "",
    }
    text = rule_explanation(rule, FIELDS)
    assert "951,89" in text and "786,69" in text and "165,20" in text


def test_amount_matches_order_pass_includes_order_and_currency():
    rule = {
        "id": "amount_matches_order",
        "state": "PASS",
        "evidence": {"invoice": "951,89", "erp": "951.89", "currency": "EUR", "tolerance": "0.01"},
        "question": "", "message": "",
    }
    text = rule_explanation(rule, FIELDS)
    assert "PO-2026-0071" in text and "951,89" in text and "EUR" in text


def test_invoice_date_pass_shows_value():
    rule = {"id": "invoice_date", "state": "PASS", "evidence": {"invoice": "2026-05-24", "as_of": "2026-09-19"}, "question": "", "message": ""}
    text = rule_explanation(rule, FIELDS)
    assert "2026-05-24" in text and "válida" in text


def test_erp_pending_pass_names_order():
    rule = {
        "id": "erp_pending",
        "state": "PASS",
        "evidence": {"erp": {"pedido": "PO-2026-0071", "estado": "PENDIENTE"}},
        "question": "", "message": "",
    }
    text = rule_explanation(rule, FIELDS)
    assert "PO-2026-0071" in text and "PENDIENTE" in text


def test_document_instructions_pass_says_no_orders():
    rule = {"id": "document_instructions", "state": "PASS", "evidence": {"matches": []}, "question": "", "message": ""}
    text = rule_explanation(rule, FIELDS)
    assert "órdenes" in text or "ordenes" in text or "instruc" in text


def test_fail_amount_still_reports_numbers():
    rule = {
        "id": "amount_matches_order",
        "state": "FAIL",
        "evidence": {"invoice": "951,89", "erp": "1000.00", "currency": "EUR", "tolerance": "0.01"},
        "question": "Aclara el importe del pedido o aporta factura corregida.",
        "message": "",
    }
    text = rule_explanation(rule, FIELDS)
    assert "no coincide" in text and "951,89" in text and "1.000,00" in text


def test_missing_field_falls_back_gracefully():
    empty = {
        "invoice_number": {"status": "MISSING", "value": None},
        "iban": {"status": "MISSING", "value": None},
        "total": {"status": "MISSING", "value": None},
        "order": {"status": "MISSING", "value": None},
        "date": {"status": "MISSING", "value": None},
        "base": {"status": "MISSING", "value": None},
        "tax_rate": {"status": "MISSING", "value": None},
        "tax_amount": {"status": "MISSING", "value": None},
        "currency": {"status": "MISSING", "value": None},
        "supplier_nif": {"status": "MISSING", "value": None},
    }
    rule = {"id": "field:iban", "state": "PASS", "evidence": {}, "question": "", "message": ""}
    text = rule_explanation(rule, empty)
    assert text == GENERIC_EXPLANATION

    rule_tax = {"id": "tax_arithmetic", "state": "PASS", "evidence": {}, "question": "", "message": ""}
    assert rule_explanation(rule_tax, empty) == GENERIC_EXPLANATION


def test_broken_rule_never_raises():
    assert rule_explanation({"id": None, "state": None, "evidence": None}, None) == GENERIC_EXPLANATION
    assert rule_explanation({}, {}) == GENERIC_EXPLANATION
    assert rule_explanation({"id": "iban_matches_master", "state": "PASS"}, {}) == GENERIC_EXPLANATION
