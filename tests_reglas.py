import pytest
import datetime
from reglas import EvaluadorFacturas, FacturaExtraida

@pytest.fixture
def evaluador():
    # Inicializa el evaluador con un path ficticio para que cargue los STUBs
    return EvaluadorFacturas(excel_path="no_existe.xlsx")

def test_ocr_baja_confianza(evaluador):
    factura = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=1000.50,
        fecha=datetime.date(2026, 1, 15),
        num_factura="FAC-001",
        confianza_ocr=0.5  # Bajo el umbral (0.7)
    )
    decision = evaluador.evaluar_factura(factura)
    assert decision.decision == "ESCALAR"
    assert decision.motivo == "documento_no_confiable"

def test_sospechoso(evaluador):
    factura = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=1000.50,
        fecha=datetime.date(2026, 1, 15),
        num_factura="FAC-002",
        sospechoso=True
    )
    decision = evaluador.evaluar_factura(factura)
    assert decision.decision == "ESCALAR"
    assert decision.motivo == "documento_no_confiable"

def test_proveedor_no_encontrado(evaluador):
    factura = FacturaExtraida(
        proveedor="PROVEEDOR DESCONOCIDO",
        importe=100.00,
        fecha=datetime.date(2026, 2, 1),
        num_factura="FAC-003"
    )
    decision = evaluador.evaluar_factura(factura)
    assert decision.decision == "ESCALAR"
    assert decision.motivo == "proveedor_no_encontrado"

def test_importe_discrepante(evaluador):
    factura = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=9999.99, # No coincide con 1000.50 ni 500.00
        fecha=datetime.date(2026, 3, 1),
        num_factura="FAC-004"
    )
    decision = evaluador.evaluar_factura(factura)
    assert decision.decision == "NO_PAGAR"
    assert decision.motivo == "importe_no_coincide"

def test_norma_no_cumplida(evaluador):
    # PROVEEDOR B está bloqueado en los stubs
    factura = FacturaExtraida(
        proveedor="PROVEEDOR B",
        importe=100.00,
        fecha=datetime.date(2026, 3, 15),
        num_factura="FAC-005"
    )
    decision = evaluador.evaluar_factura(factura)
    assert decision.decision == "NO_PAGAR"
    assert decision.motivo == "norma_incumplida: proveedor_bloqueado"

def test_duplicado_historico(evaluador):
    # El STUB tiene PROVEEDOR A, 1000.50, "FAC-25-001" en 2025_OLD
    factura = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=1000.50,
        fecha=datetime.date(2026, 4, 1),
        num_factura="FAC-25-001"
    )
    decision = evaluador.evaluar_factura(factura)
    assert decision.decision == "ESCALAR"
    assert decision.motivo == "posible_duplicado"
    assert decision.duplicado_sospechoso is True

def test_duplicado_sesion(evaluador):
    factura = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=500.00,
        fecha=datetime.date(2026, 5, 1),
        num_factura="FAC-NEW-123"
    )
    # Primera vez debe pasar
    decision1 = evaluador.evaluar_factura(factura)
    assert decision1.decision == "PAGAR"
    
    # Segunda vez debe fallar por duplicado en memoria
    decision2 = evaluador.evaluar_factura(factura)
    assert decision2.decision == "ESCALAR"
    assert decision2.motivo == "posible_duplicado"
    assert decision2.duplicado_sospechoso is True

def test_factura_correcta(evaluador):
    # Coincide con Pedido 2 de PROVEEDOR A en los STUBs
    factura = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=500.00,
        fecha=datetime.date(2026, 5, 10),
        num_factura="FAC-CORRECTA-888"
    )
    decision = evaluador.evaluar_factura(factura)
    assert decision.decision == "PAGAR"
    assert decision.motivo == "proveedor_validado_y_importe_coincide"
    assert decision.confianza == 1.0
    assert len(decision.razonamiento) == 5 # Pasó los 5 pasos de razonamiento
