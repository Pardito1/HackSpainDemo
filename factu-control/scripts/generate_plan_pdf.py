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
            fontName=FONT_BOLD,
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            spaceAfter=5,
            tracking=1.1,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName=FONT_BOLD,
            fontSize=29,
            leading=34,
            textColor=GREEN,
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName=FONT_REGULAR,
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#34483f"),
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=GREEN,
            spaceBefore=2,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
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
            spaceAfter=6,
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
    story += [metrics, Spacer(1, 14)]
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
    story += [Spacer(1, 8), p("Las distribuciones 435 / 9 / 56 (Lote 1) y 24 / 1 / 15 (Lote 2) son ejecuciones concretas con política v3 y fuentes registradas (cortes del 19 y 20-09-2026, MacBook Air M1, ERP con latencia real). No son métricas de precisión ni pagos reales. Coste externo de inferencia: 0 € — RapidOCR y las reglas corren en local.", "small")]
    story.append(PageBreak())

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
    story += [chain, Spacer(1, 14)]
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
    story.append(card("Excepción segura", "Una factura sin moneda solo puede ser NO_PAGAR si su pedido e identidad están verificados y el asiento ERP más reciente, único y consistente ya está PAGADA. No mueve dinero.", SAND))
    story.append(PageBreak())

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
    story += [trace, Spacer(1, 14)]
    story += section("Historia ERP: un caso defendible", "PO-2026-0071")
    story.append(p("El bridge devuelve PENDIENTE en mayo y PAGADA en septiembre. FactU conserva ambas filas y selecciona la de septiembre solo si pedido, proveedor, NIF e importe concuerdan y la fecha máxima es única. Fecha empatada/malformada, estado desconocido o identidad/importe contradictorio implica ESCALAR. Así no se borra un antecedente ni se toma simplemente la ultima fila.", "body"))
    story += [card("Seguridad contra instrucciones en PDF", "El contenido del PDF es dato no fiable. No puede cambiar la norma, editar proveedores, ordenar PAGAR/NO_PAGAR, llamar al ERP ni ocultar evidencia. Las instrucciones sospechosas son una causa de ESCALAR; el aislamiento de capacidades es la defensa principal.", SAND), Spacer(1, 10)]
    story.append(p("Estados técnicos y decisiones están separados: READY/RUNNING/RETRY_WAIT/ERROR no son PAGAR/NO_PAGAR/ESCALAR. Un error del ERP u OCR queda pendiente y bloquea exportación, no se presenta como una duda de negocio.", "body"))
    story.append(PageBreak())

    story += section("Seis decisiones que se pueden defender", "ADRs")
    adr_rows = [
        ("ADR-01", "Reglas explícitas y abstención", "OCR/modelos leen; el código versionado decide. PDF no es política."),
        ("ADR-02", "Lectura local selectiva", "Texto nativo antes que OCR; evidencias geométricas; menor coste y exposición."),
        ("ADR-03", "ERP completo e historial prudente", "HTTP paginado y snapshot íntegro; historial resuelto solo cuando es consistente."),
        ("ADR-04", "Estado durable y recuperación", "SQLite WAL, cola, lease, caché y bloqueo. Un escritor declarado, no distribución fingida."),
        ("ADR-05", "Revisión progresiva y trazable", "Correcciones con actor, motivo, evidencia, vista previa y caducidad si cambian hechos."),
        ("ADR-06", "Perfil Lote 2 evaluado y acotado", "RapidOCR testigo por defecto crítico, guardrails multimoneda y evaluación trazable."),
    ]
    adr_table_rows = [[p(code, "h2"), p(title, "h2"), p(reason, "card")] for code, title, reason in adr_rows]
    adrs = Table(adr_table_rows, colWidths=[2.2 * cm, 5.2 * cm, 9.1 * cm])
    adrs.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white), ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [adrs, Spacer(1, 14)]
    story += section("Medir sin vender humo", "Evaluación Lote 2")
    metrics2 = Table(
        [[metric("99.0 %", "exact match macro de campos"), metric("8 / 10", "autoaceptados correctos en holdout"), metric("31 / 40", "cobertura segura del lote")]],
        colWidths=[5.3 * cm, 5.3 * cm, 5.3 * cm],
    )
    metrics2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAGE), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [metrics2, Spacer(1, 8)]
    story.append(p("Métrica del perfil completo frente a transcripciones manuales internas revisadas: holdout retrospectivo interno de 10 documentos, agrupado por proveedor. Los template_id actuales derivan del proveedor; no prueban independencia de layout visual. 31/38 es la cobertura entre expedientes elegibles. No mide pagos, RapidOCR aislado, precisión privada ni generalización universal. El siguiente lote repite el protocolo antes de cambiar umbrales.", "small"))
    story.append(PageBreak())

    story += section("Demo ganadora en diez minutos", "Cómo contarlo")
    demo_rows = [
        [p("0:00 - 2:00", "h2"), p("Abrir la bandeja del Lote 2. Decir 24 / 1 / 15 y aclarar que es una ejecución, no accuracy. Elegir una factura JPY o sin moneda.", "card")],
        [p("2:00 - 4:00", "h2"), p("Seguir PDF, lectura nativa, testigo OCR y regla. Mostrar que manuscrito/tachón o texto que intenta mandar al agente bloquea PAGAR.", "card")],
        [p("4:00 - 6:00", "h2"), p("Abrir PO-2026-0071: dos asientos conservados, selección trazable del PAGADA más reciente y NO_PAGAR seguro.", "card")],
        [p("6:00 - 8:00", "h2"), p("Preparar un cambio de fuente en una copia de estado: vista previa de impacto, decisiones afectadas y OCR reutilizado.", "card")],
        [p("8:00 - 10:00", "h2"), p("Fallar la demo sintética entre extracción y commit; reanudar con lease. Cerrar con límites y siguiente paso de validación privada.", "card")],
    ]
    demo = Table(demo_rows, colWidths=[3.1 * cm, 13.4 * cm])
    demo.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (0, -1), SAGE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [demo, Spacer(1, 15)]
    story.append(card("Frase de cierre", "El OCR aumenta la cobertura; las reglas limitan qué puede automatizarse. Cuando falta prueba, FactU no inventa: explica la duda, conserva el contexto y deja una resolución verificable.", SAND))
    story += [Spacer(1, 12), p("Límites declarados: app local, un escritor, sin SSO/RBAC/cifrado/WORM ni pagos reales. La referencia privada y cualquier nueva norma requieren evaluación antes de ampliar automatización.", "small")]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build()
    print(OUTPUT)
