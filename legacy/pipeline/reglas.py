"""P2 - REGLAS + EXCEL.

Responsable: cruzar CamposExtraidos con proveedores.xlsx (determinista,
SIN LLM) y aplicar normas de pago -> DecisionParcial.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.interfaces import (
    CamposExtraidos,
    DecisionParcial,
    DecisionParcialTipo,
)


def aplicar_reglas(campos: CamposExtraidos, ruta_excel: Path) -> DecisionParcial:
    """Stub P2. Decisiones de ejemplo segun file_id, no lee el Excel aun.

    TODO(P2): Implementar logica real:
      - Cargar proveedores.xlsx (openpyxl/pandas) y normalizar columnas caoticas.
      - Cruzar por NIF / nombre / IBAN segun las normas del hackathon.
      - Aplicar reglas de pago (importes, IVA, fechas, listas blancas/negras).
      - Devolver PAGAR o NO_PAGAR solo con evidencia determinista.
      - Si falta dato, proveedor no cuadra o hay senal de riesgo de P1:
        INDETERMINADO + `que_falta` concreto (no un "no se" generico).
      - No llamar al ERP ni al LLM desde aqui.
    """
    excel_presente = ruta_excel.exists()
    nota_excel = (
        f"Excel encontrado en {ruta_excel}."
        if excel_presente
        else f"Excel no encontrado ({ruta_excel}); stub usa tabla ficticia."
    )

    if campos.senales_riesgo.indicios_inyeccion:
        return DecisionParcial(
            file_id=campos.file_id,
            decision=DecisionParcialTipo.INDETERMINADO,
            razonamiento=(
                f"{nota_excel} Texto libre con sospecha de inyeccion: no se usa "
                "como criterio de pago. Falta revision humana."
            ),
            confianza=0.35,
            que_falta=[
                "Confirmacion humana de que el concepto/observaciones no alteran el pago",
                "Cruce ERP del asiento real",
            ],
            proveedor_en_excel=True,
            coincidencias_excel={"fuente": "stub"},
        )

    if campos.file_id == "factura_001.pdf":
        return DecisionParcial(
            file_id=campos.file_id,
            decision=DecisionParcialTipo.PAGAR,
            razonamiento=(
                f"{nota_excel} Proveedor en lista, importe e IVA coherentes "
                "(ejemplo stub)."
            ),
            confianza=0.91,
            proveedor_en_excel=True,
            coincidencias_excel={"nif": campos.nif_proveedor, "fuente": "stub"},
        )

    if campos.file_id == "factura_002.pdf":
        return DecisionParcial(
            file_id=campos.file_id,
            decision=DecisionParcialTipo.NO_PAGAR,
            razonamiento=(
                f"{nota_excel} Proveedor no esta en el maestro de ejemplo y "
                "el documento parece manipulado."
            ),
            confianza=0.88,
            proveedor_en_excel=False,
            coincidencias_excel={"fuente": "stub"},
        )

    return DecisionParcial(
        file_id=campos.file_id,
        decision=DecisionParcialTipo.INDETERMINADO,
        razonamiento=f"{nota_excel} Caso no cubierto por el stub de normas.",
        confianza=0.4,
        que_falta=["Norma real", "Fila de Excel", "Contexto ERP"],
        proveedor_en_excel=None,
    )
