"""Plain-language labels. Presentation never modifies source facts or decisions."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

FIELDS_ES = {"invoice_number":"Número de factura", "supplier_nif":"NIF del proveedor",
    "iban":"Cuenta bancaria (IBAN)", "order":"Pedido", "date":"Fecha de emisión",
    "base":"Base imponible", "tax_rate":"Tipo de IVA", "tax_amount":"Cuota de IVA",
    "total":"Total", "currency":"Moneda"}
RESULTS_ES = {"PAGAR":"Propuesta de pago", "NO_PAGAR":"No pagar", "ESCALAR":"Consultar a Alberto",
    "PENDING":"Por procesar", "WAITING_ERP":"Esperando al ERP", "RECEIVED":"Recibida",
    "EXTRACTED":"Por comprobar", "HUMAN_REVIEW":"Consultar a Alberto", "DECIDED":"Comprobada",
    "RUNNING":"En proceso", "ERROR":"Requiere recuperación", "RETRY_WAIT":"Reintento pendiente"}
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
        return f"{Decimal(str(value)):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (ValueError, InvalidOperation):
        return str(value)

def decorate_dashboard(service, data):
    masters = {b["id"]: service.store.source(b["master_id"]) for b in data["batches"]}
    for item in data["documents"]:
        found = {s["name"] for rows in masters[item["batch_id"]]["suppliers"].values() for s in rows if s["nif"] == item["nif"]}
        item["supplier"] = next(iter(found)) if len(found) == 1 else "Proveedor por confirmar"
    data["documents"].sort(key=lambda d: ({None:0, "ESCALAR":1, "NO_PAGAR":2, "PAGAR":3}.get(d["result"],4),d["file_id"]))
    return data
