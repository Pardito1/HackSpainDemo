import datetime
from dataclasses import asdict
import json
from reglas import EvaluadorFacturas, FacturaExtraida

def main():
    evaluador = EvaluadorFacturas(excel_path="no_existe.xlsx")
    
    # Ejemplo 1: Factura Perfecta (PAGAR)
    factura_1 = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=1000.50,
        fecha=datetime.date(2026, 10, 1),
        num_factura="FAC-PERFECTA-01"
    )
    decision_1 = evaluador.evaluar_factura(factura_1)
    
    # Ejemplo 2: Factura de Proveedor Bloqueado (NO_PAGAR)
    factura_2 = FacturaExtraida(
        proveedor="PROVEEDOR B",
        importe=500.00,
        fecha=datetime.date(2026, 10, 2),
        num_factura="FAC-BLOQUEADA-02"
    )
    decision_2 = evaluador.evaluar_factura(factura_2)
    
    # Ejemplo 3: Factura con OCR dudoso e importe incorrecto (INDETERMINADO)
    factura_3 = FacturaExtraida(
        proveedor="PROVEEDOR A",
        importe=9999.99,
        fecha=datetime.date(2026, 10, 3),
        num_factura="FAC-DUDOSA-03",
        confianza_ocr=0.4
    )
    decision_3 = evaluador.evaluar_factura(factura_3)

    print("=" * 60)
    print("EJEMPLO 1: FACTURA CORRECTA (PAGAR)")
    print(json.dumps(asdict(decision_1), indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    print("EJEMPLO 2: PROVEEDOR BLOQUEADO (NO_PAGAR)")
    print(json.dumps(asdict(decision_2), indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("EJEMPLO 3: OCR BAJO Y DISCREPANCIA (ESCALAR)")
    print(json.dumps(asdict(decision_3), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
