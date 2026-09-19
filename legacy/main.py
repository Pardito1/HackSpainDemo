#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orquestador del esqueleto: P1 -> P2 -> P3 -> P4.

No contiene logica de negocio. Solo:
  - recorre facturas,
  - verifica duplicados (P3) ANTES de extraer,
  - llama las interfaces en orden,
  - consolida PAGAR / NO_PAGAR / ESCALAR y preguntas,
  - reintenta si un modulo lanza excepcion (estado ERROR -> otra pasada).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict
from pathlib import Path

from pipeline.erp_estado import consultar_erp, transicionar_estado, verificar_duplicado
from pipeline.extraccion import extraer_campos
from pipeline.interfaces import (
    VERSION_ERP,
    VERSION_MANUAL,
    VERSION_NORMA,
    CamposExtraidos,
    DecisionParcial,
    DecisionParcialTipo,
    EstadoProceso,
    Outcome,
    Pregunta,
    ResultadoERP,
    ResultadoFinal,
    Traza,
)
from pipeline.reglas import aplicar_reglas
from pipeline.salida import escribir_salidas

RAIZ = Path(__file__).resolve().parent
DIR_OUTPUTS = RAIZ / "outputs"
DIR_ESTADO = RAIZ / "estado"
DIR_PDFS = RAIZ / "entradas"
EXCEL_DEFAULT = RAIZ / "proveedores.xlsx"
MAX_REINTENTOS = 3

# Facturas de demostracion del esqueleto (existen como file_id aunque no haya PDF).
FACTURAS_DEMO = [
    "factura_001.pdf",
    "factura_002.pdf",
    "factura_003.pdf",
]


def consolidar_decision(
    campos: CamposExtraidos,
    parcial: DecisionParcial,
    erp: ResultadoERP,
) -> Outcome:
    """Une P2 + P3 + senales de P1 en un result de La Caja.

    Vive en el orquestador a proposito: ningun modulo decide el `result`
    final por su cuenta. Si hay duda o inyeccion -> ESCALAR + Pregunta.
    """
    extras = {
        "proveedor": campos.proveedor,
        "importe": campos.importe,
        "numero_factura": campos.numero_factura,
        "decision_parcial": parcial.decision.value,
        "erp_encontrado": erp.encontrado,
        "erp_asiento": erp.asiento_id,
        "uso_ocr": campos.uso_ocr,
        "confianza_ocr": campos.confianza_ocr,
    }

    if campos.senales_riesgo.indicios_inyeccion:
        return Outcome(
            file_id=campos.file_id,
            result=ResultadoFinal.ESCALAR,
            razonamiento=(
                f"{parcial.razonamiento} | ERP: {erp.notas}. "
                "Documento con indicios de inyeccion: no se paga en automatico."
            ),
            confianza=min(parcial.confianza, 0.4),
            preguntas=[
                Pregunta(
                    texto="El bloque de observaciones es ruido o una instruccion real de pago?",
                    evidencia=[campos.senales_riesgo.detalle],
                )
            ],
            extras=extras,
        )

    if parcial.decision == DecisionParcialTipo.PAGAR and erp.encontrado:
        return Outcome(
            file_id=campos.file_id,
            result=ResultadoFinal.PAGAR,
            razonamiento=(
                f"{parcial.razonamiento} | ERP confirma asiento "
                f"{erp.asiento_id} ({erp.estado_asiento})."
            ),
            confianza=parcial.confianza,
            extras=extras,
        )

    if parcial.decision == DecisionParcialTipo.NO_PAGAR:
        return Outcome(
            file_id=campos.file_id,
            result=ResultadoFinal.NO_PAGAR,
            razonamiento=f"{parcial.razonamiento} | ERP: {erp.notas}",
            confianza=parcial.confianza,
            extras=extras,
        )

    preguntas = [
        Pregunta(texto=item, evidencia=parcial.que_falta)
        for item in (parcial.que_falta or ["Falta evidencia para cerrar la decision"])
    ]
    return Outcome(
        file_id=campos.file_id,
        result=ResultadoFinal.ESCALAR,
        razonamiento=f"{parcial.razonamiento} | ERP: {erp.notas}",
        confianza=parcial.confianza,
        preguntas=preguntas,
        extras=extras,
    )


def construir_traza(
    registro_timestamps: dict,
    campos: CamposExtraidos,
    parcial: DecisionParcial,
    erp: ResultadoERP,
    outcome: Outcome,
) -> Traza:
    return Traza(
        file_id=campos.file_id,
        estado=EstadoProceso.HECHO,
        timestamps=registro_timestamps,
        evidencia={
            "campos": {
                "proveedor": campos.proveedor,
                "importe": campos.importe,
                "iva": campos.iva,
                "fecha": campos.fecha,
                "numero_factura": campos.numero_factura,
                "texto_libre": [asdict(c) for c in campos.campos_texto_libre],
                "senales_riesgo": asdict(campos.senales_riesgo),
            },
            "reglas": {
                "decision": parcial.decision.value,
                "confianza": parcial.confianza,
                "que_falta": parcial.que_falta,
            },
            "resultado": outcome.result.value,
            "preguntas": [asdict(p) for p in outcome.preguntas],
        },
        versiones={
            "norma": VERSION_NORMA,
            "erp": VERSION_ERP,
            "manual": VERSION_MANUAL,
        },
        consultas_erp=[asdict(c) for c in erp.consultas],
    )


def outcome_necesita_pregunta(campos: CamposExtraidos, parcial: DecisionParcial) -> bool:
    return campos.senales_riesgo.indicios_inyeccion or bool(parcial.que_falta)


def procesar_una(
    file_id: str,
    ruta_pdf: Path,
    ruta_excel: Path,
    duplicados_acumulados: list,
) -> None:
    """Transaccion completa de una factura. Si falla, queda en ERROR."""
    dup = verificar_duplicado(file_id, DIR_ESTADO)
    if dup.es_duplicado:
        duplicados_acumulados.append(dup)
        print(f"[skip] {file_id}: duplicado ({dup.motivo})")
        return

    transicionar_estado(file_id, EstadoProceso.PENDIENTE, DIR_ESTADO)
    transicionar_estado(file_id, EstadoProceso.PROCESANDO, DIR_ESTADO)

    campos = extraer_campos(ruta_pdf, file_id)
    parcial = aplicar_reglas(campos, ruta_excel)
    erp = consultar_erp(campos)

    if parcial.decision == DecisionParcialTipo.INDETERMINADO or outcome_necesita_pregunta(
        campos, parcial
    ):
        transicionar_estado(file_id, EstadoProceso.PENDIENTE_PREGUNTA, DIR_ESTADO)
        # En el esqueleto no hay respuesta humana: saltamos a decidir.
        transicionar_estado(file_id, EstadoProceso.RESPUESTA, DIR_ESTADO)

    transicionar_estado(file_id, EstadoProceso.DECIDIR, DIR_ESTADO)
    outcome = consolidar_decision(campos, parcial, erp)
    reg = transicionar_estado(file_id, EstadoProceso.HECHO, DIR_ESTADO)
    traza = construir_traza(reg.timestamps, campos, parcial, erp, outcome)
    escribir_salidas(outcome, traza, DIR_OUTPUTS, duplicados_acumulados)
    print(f"[ok]   {file_id} -> {outcome.result.value} (conf={outcome.confianza})")


def procesar_con_reintentos(
    file_id: str,
    ruta_pdf: Path,
    ruta_excel: Path,
    duplicados_acumulados: list,
) -> None:
    ultimo = None
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            procesar_una(file_id, ruta_pdf, ruta_excel, duplicados_acumulados)
            return
        except Exception as exc:  # el orquestador aisla fallos por factura
            ultimo = exc
            transicionar_estado(
                file_id,
                EstadoProceso.ERROR,
                DIR_ESTADO,
                error=repr(exc),
            )
            print(f"[error] {file_id} intento {intento}/{MAX_REINTENTOS}: {exc}")
            time.sleep(0.2 * intento)
    print(f"[fail] {file_id} agoto reintentos: {ultimo}")


def listar_facturas(solo_demo: bool) -> list[tuple[str, Path]]:
    if not solo_demo and DIR_PDFS.exists():
        pdfs = sorted(DIR_PDFS.glob("*.pdf"))
        if pdfs:
            return [(p.name, p) for p in pdfs]
    return [(fid, DIR_PDFS / fid) for fid in FACTURAS_DEMO]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Esqueleto de decision de facturas")
    parser.add_argument(
        "--excel",
        type=Path,
        default=EXCEL_DEFAULT,
        help="Ruta a proveedores.xlsx (P2)",
    )
    parser.add_argument(
        "--reset-outputs",
        action="store_true",
        help="Borra outcomes/trazabilidad de outputs/ antes de escribir",
    )
    parser.add_argument(
        "--solo-demo",
        action="store_true",
        help="Fuerza las 3 facturas de ejemplo aunque haya PDFs en entradas/",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv or sys.argv[1:])
    DIR_OUTPUTS.mkdir(parents=True, exist_ok=True)
    DIR_ESTADO.mkdir(parents=True, exist_ok=True)
    DIR_PDFS.mkdir(parents=True, exist_ok=True)

    if args.reset_outputs:
        for nombre in ("outcomes.jsonl", "trazabilidad.jsonl"):
            ruta = DIR_OUTPUTS / nombre
            if ruta.exists():
                ruta.unlink()

    duplicados: list = []
    for file_id, ruta_pdf in listar_facturas(solo_demo=args.solo_demo):
        procesar_con_reintentos(file_id, ruta_pdf, args.excel, duplicados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
