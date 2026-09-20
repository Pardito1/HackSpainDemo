#!/usr/bin/env python3
"""Generate the current, self-contained architecture and ADR plan PDF."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import SimpleDocTemplate


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "albertitos_plan.pdf"
GREEN = colors.HexColor("#174a3e")
MUTED = colors.HexColor("#61736c")
PAPER = colors.HexColor("#fbfaf5")
SAGE = colors.HexColor("#edf0df")
SAND = colors.HexColor("#f7edd8")
LINE = colors.HexColor("#d8ddd4")
FONT_REGULAR = "FactU-DejaVu"
FONT_BOLD = "FactU-DejaVu-Bold"


def _find_font(filename: str) -> str:
    candidates = [Path("/usr/share/fonts/truetype/dejavu") / filename]
    spec = importlib.util.find_spec("matplotlib")
    if spec and spec.origin:
        candidates.append(Path(spec.origin).parent / "mpl-data" / "fonts" / "ttf" / filename)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"No se encuentra {filename} en {candidates}")


def register_fonts():
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, _find_font("DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, _find_font("DejaVuSans-Bold.ttf")))


def styles():
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "eyebrow",
            parent=base["Normal"],
            keepWithNext=1,
            fontName=FONT_BOLD,
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            spaceAfter=3,
            tracking=1.1,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName=FONT_BOLD,
            fontSize=29,
            leading=34,
            textColor=GREEN,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName=FONT_REGULAR,
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#34483f"),
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            keepWithNext=1,
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=GREEN,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            keepWithNext=1,
            fontName=FONT_BOLD,
            fontSize=10,
            leading=13,
            textColor=GREEN,
            spaceBefore=5,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=9.2,
            leading=13.2,
            textColor=colors.HexColor("#273b34"),
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=7.8,
            leading=10.5,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "card": ParagraphStyle(
            "card",
            parent=base["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=8.6,
            leading=12,
            textColor=colors.HexColor("#273b34"),
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "metric": ParagraphStyle(
            "metric",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=18,
            leading=21,
            textColor=GREEN,
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "metric_label": ParagraphStyle(
            "metric_label",
            parent=base["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=7.6,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


register_fonts()
S = styles()


def p(text, style="body"):
    return Paragraph(text, S[style])


def section(title, eyebrow=None):
    items = []
    if eyebrow:
        items.append(p(eyebrow.upper(), "eyebrow"))
    items.append(p(title, "h1"))
    return items


def card(title, text, fill=SAGE):
    table = Table(
        [[p(title, "h2")], [p(text, "card")]],
        colWidths=[8.25 * cm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def metric(value, label):
    return [p(value, "metric"), p(label, "metric_label")]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.35)
    canvas.line(doc.leftMargin, 1.45 * cm, A4[0] - doc.rightMargin, 1.45 * cm)
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_REGULAR, 7.5)
    canvas.drawString(doc.leftMargin, 0.95 * cm, "FactU / Arquitectura y ADRs / v0.10.0 / 20.09.2026")
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.95 * cm, str(doc.page))
    canvas.restoreState()


def build():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        title="FactU - Arquitectura y ADRs v0.10.0",
        author="Equipo FactU",
        leftMargin=1.7 * cm,
        rightMargin=1.7 * cm,
        topMargin=1.55 * cm,
        bottomMargin=2.1 * cm,
    )
    story = []

    story += [p("01 / ARQUITECTURA", "eyebrow"), p("La mesa de las<br/>cuentas claras.", "title")]
    story.append(
        p(
            "FactU automatiza la comprobación de facturas y conserva las pruebas "
            "para reproducir cada decisión. Propone <b>PAGAR</b>, <b>NO_PAGAR</b> "
            "o <b>ESCALAR</b>; no transfiere dinero ni modifica el ERP.",
            "subtitle",
        )
    )
    story.append(HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=12))
    metrics = Table(
        [[metric("435 / 9 / 56", "Lote 1 (500 PDFs, 53,8 s): PAGAR / NO_PAGAR / ESCALAR"), metric("24 / 1 / 15", "Lote 2 (40 PDFs, 8,3 s): PAGAR / NO_PAGAR / ESCALAR"), metric("359 + 15", "pruebas Python y Node superadas")]],
        colWidths=[5.3 * cm, 5.3 * cm, 5.3 * cm],
    )
    metrics.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAGE), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [metrics, Spacer(1, 5)]
    story += section("Cuatro pasos con contexto", "Flujo implementado")
    steps = [
        ("P1 - Leer", "Conservar PDF, palabras, coordenadas y candidato normalizado. Texto nativo primero; OCR local solo cuando añade evidencia."),
        ("P2 - Comprobar", "Cruzar NIF, IBAN, pedido, importe, IVA, fecha, moneda, duplicados y estado ERP con reglas versionadas y Decimal."),
        ("P3 - Conservar", "Guardar fuentes, snapshot, perfil de extracción, coste, eventos append-only, caché y decisiones de forma verificable."),
        ("P4 - Resolver", "Enseñar a Alberto una razón y evidencia accionables. La corrección humana conserva el dato original y vuelve a evaluar el expediente."),
    ]
    grid = []
    for i in range(0, len(steps), 2):
        row = [card(*steps[i]), card(*steps[i + 1])]
        grid.append(row)
    table = Table(grid, colWidths=[8.25 * cm, 8.25 * cm], rowHeights=[3.25 * cm, 3.25 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(table)
    story += [Spacer(1, 5), p("Las distribuciones 435 / 9 / 56 (Lote 1) y 24 / 1 / 15 (Lote 2) son ejecuciones concretas con política v3 y fuentes registradas (cortes del 19 y 20-09-2026, MacBook Air M1, ERP con latencia real). No son métricas de precisión ni pagos reales. Coste externo de inferencia: 0 € — RapidOCR y las reglas corren en local.", "small")]
    story += section("Quien lee, quien decide, quien resuelve", "Reparto de responsabilidades")
    reparto_rows = [
        [p("Código determinista", "h2"), p("<b>Decide.</b> Único que emite PAGAR / NO_PAGAR / ESCALAR. Reglas versionadas en política JSON, aritmética con Decimal y tolerancia explicita. Ningún modelo puede cambiar una regla.", "card")],
        [p("Modelos de lectura", "h2"), p("<b>Leen.</b> PyMuPDF sobre texto nativo; RapidOCR/ONNX local como segundo testigo cuando la lectura tiene defectos. Aportan valor, página, bbox y confianza. Nunca deciden.", "card")],
        [p("Personas (Alberto)", "h2"), p("<b>Resuelven.</b> Corrección de lectura y respuesta de negocio, separadas, con actor, motivo y evidencia obligatorios. No pueden saltarse los controles bancarios ni los de duplicado.", "card")],
    ]
    reparto = Table(reparto_rows, colWidths=[4.0 * cm, 12.5 * cm])
    reparto.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (0, -1), SAGE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [reparto, Spacer(1, 5)]


    story += section("Lote 2: más lectura, no más riesgo", "Perfil de extracción aislado")
    story.append(
        p(
            "El runner valida exactamente 40 PDFs, Excel, dos CSV incrementales y la actualización del ERP. "
            "Fija <b>lote2_ocr_v1</b> en el lote; Lote 1 conserva su perfil y caché. "
            "La clave de caché incluye perfil, versión, modo y umbrales.",
            "body",
        )
    )
    chain = Table(
        [[p("PDF original", "card"), p("PyMuPDF", "card"), p("RapidOCR testigo", "card"), p("Campos con evidencia", "card"), p("Reglas", "card")]],
        colWidths=[3.25 * cm] * 5,
        hAlign="LEFT",
    )
    chain.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAGE), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story += [chain, Spacer(1, 5)]
    story += section("Criterios explícitos", "Qué se automatiza y qué no")
    choices = Table(
        [
            [p("Puede llegar a PAGAR", "h2"), p("Debe ESCALAR", "h2")],
            [
                p("Campos suficientes, EUR impreso, NIF e IBAN de maestro, pedido/importe/estado ERP coherentes, aritmética y fecha válidas, sin duplicado, anotación ni instrucción sospechosa.", "card"),
                p("Moneda ausente o ambigua; USD, JPY, GBP, CHF, BRL o MXN sin FX trazable; campo contradictorio; IBAN no autorizado; ERP ambiguo; duplicado no exacto; manuscrito o tachón.", "card"),
            ],
        ],
        colWidths=[8.25 * cm, 8.25 * cm],
        hAlign="LEFT",
    )
    choices.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), SAGE), ("BACKGROUND", (1, 0), (1, 0), SAND), ("BACKGROUND", (0, 1), (0, 1), colors.white), ("BACKGROUND", (1, 1), (1, 1), colors.white), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [choices, Spacer(1, 13)]
    story += section("Moneda y lenguaje", "Guardrail esencial")
    story.append(p("Nunca se infiere EUR por español, NIF, IBAN, país o dirección. Una factura que diga Tokyo, España puede estar en JPY. Un simbolo $ o yen sin ISO inequívoco es ambiguo. El extractor conserva el ISO visible; v3 solo permite EUR porque el ERP legado no aporta moneda ni tipo de cambio.", "body"))
    story.append(KeepTogether(card("Excepción segura", "Una factura sin moneda solo puede ser NO_PAGAR si su pedido e identidad están verificados y el asiento ERP más reciente, único y consistente ya está PAGADA. No mueve dinero.", SAND)))

    story += section("Trazabilidad que se puede seguir", "No solo logs")
    trace_rows = [
        [p("Dato", "h2"), p("Prueba conservada", "h2"), p("Uso", "h2")],
        [p("Campo de factura", "card"), p("Valor literal, normalizado, página, bbox, método, confianza y candidatos contradictorios.", "card"), p("Explicar por qué el campo entró o no en una regla.", "card")],
        [p("Excel / CSV", "card"), p("Archivo, hash, hoja, fila, celda o fila CSV registrada.", "card"), p("Identidad, proveedor y pedido sin sobrescribir la fuente.", "card")],
        [p("ERP", "card"), p("Snapshot HTTP completo, XML/páginas, latencia, reintentos y todos los asientos del pedido.", "card"), p("Estado e importe contable reproducibles.", "card")],
        [p("Regla", "card"), p("ID, versión de política, entrada, resultado PASS/FAIL/UNKNOWN y pregunta resultante.", "card"), p("Separar lectura de decisión de negocio.", "card")],
    ]
    trace = Table(trace_rows, colWidths=[3.0 * cm, 8.0 * cm, 5.5 * cm], repeatRows=1)
    trace.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SAGE), ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [trace, Spacer(1, 5)]
    story += section("Historia ERP: un caso defendible", "PO-2026-0071")
    story.append(p("El bridge devuelve PENDIENTE en mayo y PAGADA en septiembre. FactU conserva ambas filas y selecciona la de septiembre solo si pedido, proveedor, NIF e importe concuerdan y la fecha máxima es única. Fecha empatada/malformada, estado desconocido o identidad/importe contradictorio implica ESCALAR. Así no se borra un antecedente ni se toma simplemente la última fila.", "body"))
    story += [KeepTogether(card("Seguridad contra instrucciones en PDF", "El contenido del PDF es dato no fiable. No puede cambiar la norma, editar proveedores, ordenar PAGAR/NO_PAGAR, llamar al ERP ni ocultar evidencia. Las instrucciones sospechosas son una causa de ESCALAR; el aislamiento de capacidades es la defensa principal.", SAND)), Spacer(1, 6)]
    story.append(p("Estados técnicos y decisiones están separados: READY/RUNNING/RETRY_WAIT/ERROR no son PAGAR/NO_PAGAR/ESCALAR. Un error del ERP u OCR queda pendiente y bloquea exportación, no se presenta como una duda de negocio.", "body"))

    story += section("Cuanto, en que máquina y en que condiciones", "Escala y coste")
    metrics3 = Table(
        [[metric("657 doc/min", "lote completo, extremo a extremo"), metric("0,091 s", "por documento, caché frío"), metric("1.274 MiB", "pico de memoria del proceso")]],
        colWidths=[5.3 * cm, 5.3 * cm, 5.3 * cm],
    )
    metrics3.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAGE), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [metrics3, Spacer(1, 6)]
    cond_rows = [
        [p("Máquina", "h2"), p("macOS arm64, 12 CPU lógicas, Python 3.12, un solo worker de escritura. ONNX puede usar dos hilos internos.", "card")],
        [p("Medida", "h2"), p("45,63 s extremo a extremo para 500 PDFs con caché frío: 0,18 s de ingesta, 5,25 s de ERP y el resto lectura más reglas. Incluye ERP con latencia real y OCR, no solo extracción de PDF.", "card")],
        [p("Reparto de lectura", "h2"), p("493 páginas resueltas con texto nativo y 29 con OCR local. Que el OCR solo entre donde falta texto es lo que mantiene el tiempo bajo.", "card")],
        [p("Cuello de botella", "h2"), p("El ERP, no la CPU: 516 asientos en 26 páginas, 30 intentos y 3 reintentos, con límite de 10 peticiones por segundo. Un único regulador de consultas; el trafico al bridge no se multiplica por el número de workers.", "card")],
    ]
    cond = Table(cond_rows, colWidths=[3.6 * cm, 12.9 * cm])
    cond.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (0, -1), SAGE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [cond, Spacer(1, 7)]
    story.append(KeepTogether(card("Fórmula de coste", "coste_doc = (tokens_in x precio_in) + (tokens_out x precio_out), o neuronas x tarifa si el proveedor las expone. Los precios entran por variable de entorno, nunca como constante en el código. Con lectura 100% local el coste externo de inferencia es 0 EUR en los dos lotes. Un cero registrado sin tarifas configuradas no demuestra gratuidad, y falta imputar hardware y tiempo humano.", SAND)))

    story += section("Medir", "Evaluación Lote 2")
    metrics2 = Table(
        [[metric("99.0 %", "exact match macro de campos"), metric("8 / 10", "autoaceptados correctos en holdout"), metric("31 / 40", "cobertura segura del lote")]],
        colWidths=[5.3 * cm, 5.3 * cm, 5.3 * cm],
    )
    metrics2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAGE), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [metrics2, Spacer(1, 5)]
    story.append(p("Métrica del perfil completo frente a transcripciones manuales internas revisadas: holdout retrospectivo interno de 10 documentos, agrupado por proveedor. Los template_id actuales derivan del proveedor; no prueban independencia de layout visual. 31/38 es la cobertura entre expedientes elegibles. No mide pagos, RapidOCR aislado, precisión privada ni generalización universal. El siguiente lote repite el protocolo antes de cambiar umbrales.", "small"))

    story += section("Qué cambia si Alberto trae algo nuevo", "Evolución")
    evo_rows = [
        [p("Layout de PDF nuevo", "h2"), p("Configuracion y extractor sobre el mismo contrato, con pruebas negativas. La política no se toca.", "card")],
        [p("Escaneados o imagen", "h2"), p("Perfil de extracción versionado, como lote2_ocr_v1. La clave de caché incluye perfil, versión, modo y umbrales, así que el Lote 1 no se reprocesa.", "card")],
        [p("Otra fuente de datos", "h2"), p("CSV y Excel ya tienen conector explícito: el Lote 2 entró así, con dos CSV y el Excel maestro validados antes de escribir nada. Email u otros formatos piden un adaptador nuevo: es código con pruebas, no configuración, y lo decimos en vez de prometerlo.", "card")],
        [p("Norma nueva", "h2"), p("Política JSON versionada. Si la norma no cabe en extra_rules, código mínimo con test; nunca una regla implicita.", "card")],
        [p("Más volumen", "h2"), p("Blobs a almacenamiento de objetos, SQLite a PostgreSQL, cola durable, workers de extracción independientes y un publicador transaccional. Es un plan medido, no infraestructura desplegada.", "card")],
    ]
    evo = Table(evo_rows, colWidths=[3.6 * cm, 12.9 * cm])
    evo.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (0, -1), SAGE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [evo, Spacer(1, 5)]

    story += section("Qué pasa cuando algo se cae", "Resiliencia y recuperación")
    fallo_rows = [
        [p("Proveedor de modelo caído, timeout o respuesta inválida", "h2"), p("Aviso en la extracción y ESCALAR con motivo. Nunca una excepción sin capturar, nunca un result inventado, nunca una factura sin línea. La ruta local (PyMuPDF más RapidOCR) no depende de ningún proveedor: el sistema sigue decidiendo sin el, con menos cobertura y más consultas.", "card")],
        [p("Rate limit del ERP legado", "h2"), p("Ritmo acotado por debajo del límite y reintento con espera. Renovacion de sesión en 401. Un solo regulador para toda la aplicación.", "card")],
        [p("ORA-00600 cada diez consultas", "h2"), p("Reintento acotado. Medido: 30 intentos y 3 reintentos para traer 516 asientos. Una sincronización fallida no publica resultados parciales ni deja vigente una decisión anterior del lote.", "card")],
        [p("Corte a media ejecución", "h2"), p("SQLite WAL, eventos append-only encadenados, caché por contenido y versiones, y lease de 10 minutos con token de propietario. Al reanudar no se repite el trabajo hecho ni se puede robar un lease vivo.", "card")],
        [p("Duplicados", "h2"), p("Barrera: no se publica ninguna decisión hasta terminar todas las lecturas del lote, para indexar los duplicados entre lotes una sola vez.", "card")],
    ]
    fallo = Table(fallo_rows, colWidths=[4.6 * cm, 11.9 * cm])
    fallo.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (0, -1), SAGE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [fallo, Spacer(1, 7)]
    story.append(p("Estados técnicos y decisiones estan separados: READY / RUNNING / RETRY_WAIT / ERROR no son PAGAR / NO_PAGAR / ESCALAR. Un fallo de ERP u OCR queda pendiente y bloquea la exportación; no se disfraza de duda de negocio. No prometemos entrega exactamente-una-vez ni alta disponibilidad: un expediente atascado puede impedir cerrar el lote, y preferimos que ese límite se vea.", "small"))



    story += section("Cinco decisiones que se pueden defender", "ADRs y trade-offs")
    adrs_full = [
        ("ADR-01", "Reglas explícitas y abstención; sin decisor LLM",
         "Las facturas llevan texto engañoso y la norma deja parte del criterio al equipo. Un resultado muy seguro pero sin evidencia puede producir un pago indebido.",
         "Agente autónomo que decide; LLM extractor más reglas; parser y OCR más reglas con revisión humana.",
         "La tercera. PAGAR exige todos los controles; NO_PAGAR se limita a pago confirmado o copia exacta; el resto escala. El PDF es dato, nunca política: un texto que ordena pagar no cambia el veredicto, solo se registra.",
         "Reproducible y con cero inferencia facturada; a cambio, menos flexibilidad semántica y más revisión en escaneados difíciles. No afirmamos tener un orquestador multiagente ni failover de LLM.",
         "test_policy.py: instrucciones no autoritativas, tolerancia exacta, emisor frente a cliente, fuentes contradictorias, fecha inválida y chequeos de salida. Los tests no son las etiquetas del jurado."),
        ("ADR-02", "Lectura local por capas y perfil acotado por lote",
         "500 PDFs y 522 páginas, de las que 29 exigen OCR. El segundo lote añade idiomas, divisas y manipulaciones que no deben alterar lo ya comprobado en el primero.",
         "OCR a todo; servicio cloud de documentos; reentrenar un modelo con 40 ejemplos; lectura nativa más OCR local selectivo con perfil versionado por lote.",
         "La última. PyMuPDF conserva palabras y coordenadas; RapidOCR/ONNX local entra solo como segundo testigo ante defecto crítico. El Lote 2 usa el perfil aislado lote2_ocr_v1 y el Lote 1 conserva el suyo y su caché.",
         "Arranque sin claves de API, las facturas no salen de la máquina y 0 EUR de inferencia; se aceptan limites de idioma, geometría y calidad. El holdout interno es pequeño (10 documentos) y agrupado por proveedor: no prueba independencia de layout visual.",
         "Benchmark del lote completo; evaluate_lote2_ocr.py con etiquetas y splits versionados; 99,0 % de exact match macro de campos en el holdout interno."),
        ("ADR-03", "ERP por HTTP con snapshot íntegro por lote",
         "El bridge de 2009 tiene latencia, paginacion, sesiones que caducan y errores ORA-00600 deliberados. Ademas el Excel y el ERP discrepan en algunas identidades.",
         "Leer los datos internos del script; consultar el ERP factura a factura; snapshot paginado y versionado por lote.",
         "Snapshot HTTP completo, sin saltarse el bridge. Ritmo acotado, reintentos en 429, 500 y timeout, renovacion en 401 y validación de recuentos e identificadores únicos. Una sincronización fallida no publica resultados parciales.",
         "Amortiza consultas y permite reproducir decisiones, pero el snapshot tiene fecha y envejece. No existe una operación de pago contra un dato supuestamente en tiempo real; en producción haria falta una versión de corte consistente.",
         "Pruebas de 401, 429, 500, timeout y snapshot incompleto; 516 registros en 26 páginas con el ERP en modo normal. Los XML originales se conservan para inspección."),
        ("ADR-04", "SQLite, un escritor y recuperación conservadora",
         "Fin de semana de hackathon: hace falta estado durable, no perder trabajo y evitar carreras entre la CLI y la interfaz web.",
         "Estado en memoria; PostgreSQL con Redis y Celery desde el principio; SQLite WAL con cola local y bloqueo de workflow.",
         "SQLite con transacciones, eventos append-only encadenados, caché por contenido y versiones, y lease de 10 minutos con token de propietario. Un solo flujo de escritura y lecturas concurrentes.",
         "Instalacion sencilla y recuperación verificable; más volumen u operadores obligan a rediseñar la cola y coordinar un publicador transaccional. Un expediente atascado puede impedir cerrar otros lotes: preferimos hacer visible ese límite a afirmar una entrega exactamente-una-vez que no tenemos.",
         "test_service.py: reinicio entre extracción y commit, imposibilidad de robar un lease vivo, idempotencia, duplicados entre lotes y bloqueo entre instancias."),
        ("ADR-05", "Alberto resuelve con evidencia; el sistema conserva el contexto",
         "Preguntar es una salida legitima, pero resolver un campo no debe saltarse el resto de controles. Y una misma causa puede repetirse muchas veces y costar tiempo.",
         "Un boton de aprobar todo; editar el dato sobrescribiendo el original; corrección versionada con vista previa y reevaluación del expediente.",
         "La tercera. Corrección de lectura y respuesta de negocio van separadas, con actor, motivo y referencia obligatorios, y el historial queda intacto. Si cambia el fundamento, el expediente vuelve a ESCALAR y se pide ratificación.",
         "Resolucion auditable con coste humano declarado. No sustituye una identidad autenticada, no prueba la veracidad de una referencia aportada y no ejecuta pagos. PAGAR nunca salta controles de cuenta, importe, identidad ni duplicados.",
         "test_workspace.py: caducidad por cambios de contexto, confirmaciones obsoletas, restricciones de PAGAR, conservacion selectiva, borrador descargable y auditoría."),
    ]
    for code, title, ctx, alt, dec, con, ev in adrs_full:
        filas = [
            [p(code + " &middot; " + title, "h2"), ""],
            [p("Contexto", "h2"), p(ctx, "card")],
            [p("Alternativas", "h2"), p(alt, "card")],
            [p("Decisión", "h2"), p(dec, "card")],
            [p("Consecuencias", "h2"), p(con, "card")],
            [p("Evidencia", "h2"), p(ev, "card")],
        ]
        tabla = Table(filas, colWidths=[3.5 * cm, 13.0 * cm])
        tabla.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), SAND),
            ("BACKGROUND", (0, 1), (0, -1), SAGE),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story += [KeepTogether(tabla), Spacer(1, 4)]

    story.append(KeepTogether(card("Cuando falta prueba, FactU no inventa", "El OCR aumenta la cobertura; las reglas limitan qué puede automatizarse. FactU explica la duda, conserva el contexto y deja una resolución verificable.", SAND)))
    story += [Spacer(1, 7), p("Límites declarados: app local, un escritor, sin SSO/RBAC/cifrado/WORM ni pagos reales. La referencia privada y cualquier nueva norma requieren evaluación antes de ampliar automatización.", "small")]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build()
    print(OUTPUT)
