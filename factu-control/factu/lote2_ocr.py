"""Perfil de extracción conservador para el segundo lote de 40 facturas.

No es una política de pago. Este módulo conserva la lectura nativa de PyMuPDF
y, únicamente cuando se usa ``profile='lote2_ocr_v1'``, puede contrastarla con
RapidOCR. El OCR nunca reemplaza una lectura nativa válida por una lectura
dudosa: sus candidatos y sus cajas se guardan como evidencia y cualquier
contradicción de suficiente calidad se deja como ``CONFLICT`` para que la
política la escale.

El lote contiene facturas multilingües y divisas no EUR. Por ello aquí no se
deduce nunca una moneda a partir de la dirección, el idioma ni el proveedor.
Solo se acepta una ISO explícita o un símbolo no ambiguo impreso.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal

import pymupdf as fitz

from .utils import clean, identifier, invoice_date, money

PROFILE = "lote2_ocr_v1"
VERSION = "native-rapidocr-lote2-v1"
FIELD_NAMES = (
    "invoice_number",
    "supplier_nif",
    "iban",
    "order",
    "date",
    "base",
    "tax_rate",
    "tax_amount",
    "total",
)
CRITICAL_FIELDS = (*FIELD_NAMES[1:], "currency")
OCR_MODES = {"defects", "always"}
MIN_WITNESS_CONFIDENCE = 0.84
MIN_CONFLICT_CONFIDENCE = 0.92

# Etiquetas que aparecen en ES/EN/CA/PT/FR/IT/DE. Se usan solo para localizar
# valores impresos; la decisión se sigue haciendo en policy.py.
INVOICE_LABEL = (
    r"(?:factura(?:\s+simplificada)?|invoice|facture|fatura|fattura|rechnung)"
    r"\s*(?:n(?:[ºo°.]|[úu]m(?:\.|ero)?|r\.)?|n\.\s*[ºo°]|no\.?|#)?"
)
DATE_LABEL = (
    r"(?:fecha(?:\s+(?:de\s+emisi[oó]n|factura))?|date(?:\s+(?:d['’]?émission|"
    r"of\s+issue|issue))?|data(?:\s+(?:d['’]?emissi[oó]n|de\s+emiss[aã]o))?|"
    r"ausstellungsdatum)"
)
ORDER_LABEL = (
    r"(?:ref\.?\s*pedido|pedido(?:\s+(?:asociado|cliente))?|su\s+pedido|po|"
    r"purchase\s+order|bon\s+de\s+commande|comanda|encomenda|ordine|bestellung)"
)
SUPPLIER_ID_LABEL = (
    r"(?:nif|cif|tax\s*id|vat\s*id|n[ºo°.]?\s*tva|p\.?\s*iva|ust[\-\s]?id|"
    r"uid|iva)"
)
CLIENT_MARKERS = re.compile(
    r"cliente|client|bill\s*to|facturar\s*a|faturar\s*a|factur[ée]\s*[àa]|"
    r"destinatario|rechnungsempf[äa]nger",
    re.I,
)
IBAN_LABEL = re.compile(r"\biban\b|cuenta\s+(?:de\s+)?abono", re.I)

AMOUNT_LABEL = re.compile(
    r"(?<![A-Za-zÀ-ÿ])(?P<base>importe\s+base|base(?:\s+(?:imponible|imposable))?|"
    r"valor\s+base|subtotal|sous[\-\s]?total|imponibile|zwischensumme|netto)"
    r"|(?<![A-Za-zÀ-ÿ])(?P<total>importe\s+total|total(?:\s+(?:factura|a\s+pagar|due))?|"
    r"montant\s+total|totale|gesamt|valor\s+total)"
    r"|(?<![A-Za-zÀ-ÿ])(?P<tax_amount>(?:cuota\s+)?(?:[I1l]\.?V\.?A\.?|VAT|TVA|MwSt\.?|tax))",
    re.I,
)
AMOUNT_TOKEN = re.compile(
    r"(?<![\d.,])(?:[+\-−]\s*)?\d[\d.,]*(?:[ \u00a0\u202f]\d[\d.,]*)*"
)
CURRENCY_TOKEN = re.compile(
    r"(?<![A-Z0-9])(?:EUR|USD|GBP|CHF|JPY|BRL|MXN)(?![A-Z0-9])|R\$|MX\$|€|£",
    re.I,
)
IBAN_TOKEN = re.compile(r"\b([A-Z]{2}\s*\d{2}(?:\s*[A-Z0-9]){11,30})\b", re.I)
ORDER_TOKEN = re.compile(r"\bPO\s*[-–— ]\s*\d{4}\s*[-–— ]\s*\d{3,6}\b", re.I)


def _ascii(value: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", clean(value).lower())
        if not unicodedata.combining(c)
    )


def _union(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def group_lines(tokens, page_number, method):
    """Agrupa tokens de PyMuPDF o RapidOCR conservando sus coordenadas."""
    groups = []
    for token in sorted(
        tokens, key=lambda t: ((t["bbox"][1] + t["bbox"][3]) / 2, t["bbox"][0])
    ):
        box = token["bbox"]
        y = (box[1] + box[3]) / 2
        target = next(
            (
                g
                for g in reversed(groups[-3:])
                if abs(g["y"] - y) < max(3, (box[3] - box[1]) * 0.45)
            ),
            None,
        )
        if target is None:
            target = {"y": y, "tokens": []}
            groups.append(target)
        target["tokens"].append(token)
    lines = []
    for group in groups:
        words, text = sorted(group["tokens"], key=lambda t: t["bbox"][0]), ""
        for token in words:
            token["start"] = len(text)
            text += clean(token["text"])
            token["end"] = len(text)
            text += " "
        lines.append(
            {
                "text": text.strip(),
                "raw_text": " ".join(t["text"] for t in words),
                "words": words,
                "bbox": _union([t["bbox"] for t in words]),
                "page": page_number,
                "method": method,
            }
        )
    return lines


def currency_lote2(value):
    """Solo normaliza una moneda impresa de forma no ambigua.

    ``$``, ``¥`` y ``Fr`` por sí solos se ignoran deliberadamente: pueden
    designar varias monedas. En las facturas del lote aparecen junto a
    USD/JPY/CHF, que sí es la evidencia aceptable.
    """
    raw = clean(value).upper()
    mapping = {
        "€": "EUR",
        "£": "GBP",
        "R$": "BRL",
        "MX$": "MXN",
    }
    if raw in mapping:
        return mapping[raw]
    if raw in {"EUR", "USD", "GBP", "CHF", "JPY", "BRL", "MXN"}:
        return raw
    raise ValueError("Divisa no reconocida o ambigua")


def invoice_number_lote2(value):
    value = identifier(value).replace("–", "-").replace("—", "-")
    if (
        len(value) > 80
        or not re.fullmatch(r"[A-Z0-9][A-Z0-9/_-]{2,}", value)
        or not re.search(r"\d", value)
        or re.search(r"FECHA|DATE|DATA|TOTAL|PEDIDO|ORDER|NIF|CIF|IBAN", value)
    ):
        raise ValueError("Número de factura ambiguo: contiene etiquetas o campos mezclados")
    return value


def order_lote2(value):
    compact = re.sub(r"[\s–—]+", "-", clean(value).upper())
    compact = re.sub(r"-+", "-", compact)
    if not re.fullmatch(r"PO-\d{4}-\d{3,6}", compact):
        raise ValueError("Pedido ilegible o sin formato PO-AAAA-NNN")
    return compact


def supplier_id_lote2(value):
    # Conserva . / - porque el maestro puede usar el formato brasileño
    # impreso; elimina solo espacios y valida formas internacionales visibles.
    raw = identifier(value)
    if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", raw):
        return raw
    if re.fullmatch(r"(?:[A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z]|[A-Z]{2}[A-Z0-9]{7,14}|\d{10,15})", raw):
        return raw
    raise ValueError("Identificador fiscal internacional ilegible")


def iban_lote2(value):
    compact = identifier(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        raise ValueError("IBAN internacional ilegible")
    return compact


def _document_currency(lines):
    """ISO explícita única que contextualiza importes, no el campo moneda.

    Esto permite leer ``¥ 773,000`` solo cuando en el propio documento consta
    también ``JPY``. Un símbolo ¥ aislado sigue siendo ambiguo y no produce
    ninguna moneda confirmada.
    """
    codes = {
        match.group(0).upper()
        for line in lines
        for match in re.finditer(r"(?<![A-Z0-9])(?:EUR|USD|GBP|CHF|JPY|BRL|MXN)(?![A-Z0-9])", line["text"], re.I)
    }
    return next(iter(codes)) if len(codes) == 1 else None


def _line_currency(text, document_currency=None):
    # Preferimos una ISO impresa en la misma línea para poder interpretar JPY
    # con importes sin céntimos. Los símbolos solos solo se admiten si no son $.
    tokens = [m.group(0) for m in CURRENCY_TOKEN.finditer(text)]
    iso = next((t for t in tokens if t.upper() in {"EUR", "USD", "GBP", "CHF", "JPY", "BRL", "MXN"}), None)
    if iso:
        return currency_lote2(iso)
    if tokens:
        return currency_lote2(tokens[0])
    # Los símbolos $ y ¥ son ambiguos por sí solos. Sirven para interpretar
    # cifras solamente después de una ISO explícita en el mismo documento.
    if document_currency and ("$" in text or "¥" in text or "Fr" in text):
        return document_currency
    return None


def amount_lote2(value, line_currency=None):
    """Acepta céntimos impresos y los enteros con miles propios de JPY.

    La excepción JPY no reconstruye un importe: solo quita separadores de
    miles ya impresos en una línea que declara explícitamente JPY/¥.
    """
    raw = clean(value).replace("−", "-")
    try:
        return money(raw)
    except (ValueError, ArithmeticError):
        if line_currency == "JPY" and re.fullmatch(r"[+-]?\d{1,3}(?:[,.]\d{3})+", raw):
            return Decimal(raw.replace(",", "").replace(".", ""))
        raise


_MONTHS = {
    "enero": 1, "january": 1, "janvier": 1, "janeiro": 1, "gener": 1, "gennaio": 1, "januar": 1,
    "febrero": 2, "feb": 2, "february": 2, "fevrier": 2, "fevereiro": 2, "febrer": 2, "febbraio": 2, "februar": 2,
    "marzo": 3, "march": 3, "mars": 3, "marco": 3, "marc": 3, "marz": 3,
    "abril": 4, "april": 4, "avril": 4, "abril": 4, "aprile": 4,
    "mayo": 5, "may": 5, "mai": 5, "maio": 5, "maggio": 5,
    "junio": 6, "june": 6, "juin": 6, "junho": 6, "juny": 6, "giugno": 6, "juni": 6,
    "julio": 7, "july": 7, "juillet": 7, "julho": 7, "juliol": 7, "luglio": 7, "juli": 7,
    "agosto": 8, "august": 8, "aout": 8, "agost": 8, "agosto": 8,
    "septiembre": 9, "september": 9, "septembre": 9, "setembro": 9, "settembre": 9, "september": 9,
    "octubre": 10, "october": 10, "octobre": 10, "outubro": 10, "ottobre": 10, "oktober": 10,
    "noviembre": 11, "november": 11, "novembre": 11, "novembro": 11,
    "diciembre": 12, "december": 12, "decembre": 12, "dezembro": 12, "desembre": 12, "dicembre": 12, "dezember": 12,
}
_DAYS = {
    # ES/CA/PT/FR/IT/DE/EN: formas presentes en el lote y sus equivalentes
    "uno": 1, "un": 1, "one": 1, "primeiro": 1, "premier": 1, "erste": 1,
    "dos": 2, "deux": 2, "due": 2, "zwei": 2, "second": 2, "segundo": 2,
    "tres": 3, "trois": 3, "tre": 3, "three": 3, "drei": 3,
    "cuatro": 4, "quatre": 4, "quattro": 4, "four": 4, "vier": 4,
    "cinco": 5, "cinq": 5, "cinque": 5, "five": 5, "funf": 5,
    "seis": 6, "six": 6, "sei": 6, "sixth": 6, "sechste": 6,
    "siete": 7, "sete": 7, "sette": 7, "sept": 7, "seven": 7, "seventh": 7, "siebten": 7,
    "ocho": 8, "huit": 8, "otto": 8, "eight": 8, "acht": 8,
    "nueve": 9, "neuf": 9, "nove": 9, "nine": 9, "neun": 9,
    "diez": 10, "dez": 10, "dix": 10, "dieci": 10, "ten": 10, "zehn": 10,
    "once": 11, "onze": 11, "undici": 11, "eleven": 11, "elf": 11,
    "doce": 12, "douze": 12, "dodici": 12, "twelve": 12, "zwolf": 12,
    "trece": 13, "treize": 13, "tredici": 13, "thirteen": 13, "dreizehn": 13,
    "catorce": 14, "quatorze": 14, "quattordici": 14, "fourteen": 14, "vierzehn": 14,
    "quince": 15, "quinze": 15, "quindici": 15, "fifteen": 15, "funfzehnten": 15,
    "dieciseis": 16, "seize": 16, "sedici": 16, "sixteen": 16, "sechzehn": 16,
    "diecisiete": 17, "dixsept": 17, "diciassette": 17, "seventeen": 17, "siebzehn": 17,
    "dieciocho": 18, "dixhuit": 18, "diciotto": 18, "eighteen": 18, "achtzehn": 18,
    "diecinueve": 19, "dixneuf": 19, "diciannove": 19, "nineteen": 19, "neunzehn": 19,
    "veinte": 20, "vinte": 20, "vingt": 20, "venti": 20, "twenty": 20, "zwanzig": 20,
    "veintiuno": 21, "vinteeum": 21, "vingtetun": 21, "ventuno": 21, "twentyone": 21, "einundzwanzig": 21,
    "veintidos": 22, "vinteedois": 22, "vingtdeux": 22, "ventidue": 22, "twentytwo": 22, "zweiundzwanzig": 22,
    "veintitres": 23, "vinteetres": 23, "vingttrois": 23, "ventitre": 23, "twentythree": 23, "dreiundzwanzig": 23,
    "veinticuatro": 24, "vinteequatro": 24, "vingtquatre": 24, "ventiquattro": 24, "twentyfour": 24, "vierundzwanzig": 24,
    "veinticinco": 25, "vinteecinco": 25, "vingtcinq": 25, "venticinque": 25, "twentyfive": 25, "funfundzwanzig": 25,
    "veintiseis": 26, "vinteeseis": 26, "vingtsix": 26, "ventisei": 26, "twentysix": 26, "sechsundzwanzig": 26,
    "veintisiete": 27, "vinteesete": 27, "vingtsept": 27, "ventisette": 27, "twentyseven": 27, "siebenundzwanzig": 27,
    "veintiocho": 28, "vinteeoito": 28, "vingthuit": 28, "ventotto": 28, "twentyeight": 28, "achtundzwanzig": 28,
    "veintinueve": 29, "vinteenove": 29, "vingtneuf": 29, "ventinove": 29, "twentynine": 29, "neunundzwanzig": 29,
    "treinta": 30, "trinta": 30, "trente": 30, "trenta": 30, "thirty": 30, "dreissig": 30,
    "treintayuno": 31, "trintaeum": 31, "trenteetun": 31, "trentuno": 31, "thirtyone": 31, "einunddreissig": 31,
}
_YEAR_MARKERS = {
    "dosmilveintiseis": 2026,
    "dosmilvintisis": 2026,
    "doismilevinteeseis": 2026,
    "deuxmillevingtsix": 2026,
    "duemilaventisei": 2026,
    "zweitausendsechsundzwanzig": 2026,
    "twothousandtwentysix": 2026,
    "twothousandandtwentysix": 2026,
}


def date_lote2(value):
    """Normaliza fechas numéricas y las fechas literales del lote multilingüe."""
    raw = clean(value)
    try:
        return invoice_date(raw)
    except ValueError:
        pass
    text = _ascii(raw)
    numeric = re.search(r"\b(\d{1,2})\s+([a-z]+)\s*,?\s*(\d{4})\b", text)
    if numeric and numeric[2] in _MONTHS:
        return f"{int(numeric[3]):04d}-{_MONTHS[numeric[2]]:02d}-{int(numeric[1]):02d}"
    month_match = next(
        (m for m in re.finditer(r"\b[a-z]+\b", text) if m.group(0) in _MONTHS),
        None,
    )
    if not month_match:
        raise ValueError("Fecha multilingüe ilegible")
    before = re.sub(r"[^a-z0-9]", "", text[: month_match.start()])
    after = re.sub(r"[^a-z0-9]", "", text[month_match.end() :])
    day = next((number for word, number in sorted(_DAYS.items(), key=lambda item: -len(item[0])) if word in before), None)
    if day is None:
        day_match = re.search(r"\d{1,2}", text[: month_match.start()])
        day = int(day_match.group(0)) if day_match else None
    year_match = re.search(r"\b(20\d{2})\b", text[month_match.end() :])
    year = int(year_match.group(1)) if year_match else next(
        (number for marker, number in _YEAR_MARKERS.items() if marker in after),
        None,
    )
    if not day or not year or not 1 <= day <= 31:
        raise ValueError("Fecha multilingüe ilegible")
    # datetime (vía invoice_date) valida los días imposibles y conserva el
    # mismo contrato ISO que el resto de la aplicación.
    return invoice_date(f"{year:04d}-{_MONTHS[month_match.group(0)]:02d}-{day:02d}")


def _normalizer_name(normalize):
    return getattr(normalize, "__name__", normalize.__class__.__name__)


def parse_lote2_fields(lines):
    """Extrae candidatos multilingües con evidencia por campo y coordenada."""
    candidates = defaultdict(list)
    document_currency = _document_currency(lines)

    def candidate(field, raw, line, span, normalize):
        if not clean(raw):
            return
        words = [
            w for w in line["words"] if w["end"] > span[0] and w["start"] < span[1]
        ]
        bbox = _union([w["bbox"] for w in words]) if words else line["bbox"]
        scores = [w["confidence"] for w in words if w.get("confidence") is not None]
        value = error = None
        try:
            value = str(normalize(raw))
        except (ValueError, ArithmeticError) as exc:
            error = str(exc)
        candidates[field].append(
            {
                "raw_value": raw,
                "value": value,
                "error": error,
                "page": line["page"],
                "bbox": bbox,
                "coordinate_space": "pdf_points_top_left",
                "method": line["method"],
                "confidence": min(scores) if scores else None,
                "source_text": line["raw_text"],
                "transformations": ["unicode_NFKC_format_char_removal", _normalizer_name(normalize)],
            }
        )

    for line in lines:
        text = line["text"]
        line_currency = _line_currency(text, document_currency)
        for match in CURRENCY_TOKEN.finditer(text):
            candidate("currency", match.group(0), line, match.span(), currency_lote2)
        # Un $ aislado no crea una moneda. Se conserva en texto/evidencia, y
        # si no hay ISO/símbolo inequívoco el campo permanecerá MISSING.
        for match in re.finditer(r"(?<![A-Z0-9])\$(?![A-Z0-9])", text):
            if not line_currency:
                candidates["currency"].append(
                    {
                        "raw_value": match.group(0), "value": None,
                        "error": "El símbolo $ no identifica por sí solo la moneda",
                        "page": line["page"], "bbox": line["bbox"],
                        "coordinate_space": "pdf_points_top_left", "method": line["method"],
                        "confidence": None, "source_text": line["raw_text"],
                        "transformations": ["currency_requires_iso_or_unambiguous_symbol"],
                    }
                )

        for match in re.finditer(
            INVOICE_LABEL + r"\s*[:#.]?\s*([A-Z0-9][A-Z0-9/_-]{2,})", text, re.I
        ):
            raw = match[1]
            if not re.fullmatch(r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}", raw):
                candidate("invoice_number", raw, line, match.span(1), invoice_number_lote2)

        for match in ORDER_TOKEN.finditer(text):
            candidate("order", match.group(0), line, match.span(), order_lote2)
        # También se reconoce un pedido cuando la etiqueta y el identificador
        # se separan por dos puntos, tabulación o salto de lectura OCR.
        for match in re.finditer(ORDER_LABEL + r"\s*[:#.]?\s*(PO[^\s,;]{0,20})", text, re.I):
            raw = match[1]
            if not ORDER_TOKEN.fullmatch(raw):
                candidate("order", raw, line, match.span(1), order_lote2)

        date_match = re.search(DATE_LABEL + r"\s*[:.]?\s*(.+)$", text, re.I)
        if date_match:
            raw = date_match[1].strip()
            # No tomamos una etiqueta contigua como parte de una fecha larga.
            raw = re.split(r"\s+(?:" + ORDER_LABEL + r")\b", raw, maxsplit=1, flags=re.I)[0].strip()
            candidate("date", raw, line, date_match.span(1), date_lote2)

        if not CLIENT_MARKERS.search(text):
            id_match = re.search(SUPPLIER_ID_LABEL + r"\s*[:.]?\s*([A-Z0-9./-]{8,24})", text, re.I)
            if id_match:
                candidate("supplier_nif", id_match[1], line, id_match.span(1), supplier_id_lote2)

        if IBAN_LABEL.search(text):
            for match in IBAN_TOKEN.finditer(text):
                candidate("iban", match[1], line, match.span(1), iban_lote2)

        labels = list(AMOUNT_LABEL.finditer(text))
        # Una declaración comercial puede escribir un tipo distinto de la fila
        # de IVA (por ejemplo, ``0% export VAT`` frente a ``VAT (21%)``). No
        # elegimos una de las dos: ambas quedan como candidatos y el campo se
        # convierte en CONFLICT para que el motor escale la contradicción.
        for rate in re.finditer(
            r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*(?:[A-Za-zÀ-ÿ]+\s+){0,3}(?:VAT|TVA|IVA|MWST|TAX)\b",
            text,
            re.I,
        ):
            candidate("tax_rate", rate[1], line, rate.span(1), money)
        for index, label in enumerate(labels):
            # La etiqueta debe estar al inicio o seguir otra etiqueta/importe;
            # así no se confunde una frase comercial con una cifra de control.
            if index == 0 and text[: label.start()].strip():
                continue
            field = label.lastgroup
            start = label.end()
            end = labels[index + 1].start() if index + 1 < len(labels) else len(text)
            segment = text[start:end]
            rates = list(re.finditer(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", segment))
            if field == "tax_amount":
                for rate in rates:
                    candidate("tax_rate", rate[1], line, (start + rate.start(1), start + rate.end(1)), money)
            for amount in AMOUNT_TOKEN.finditer(segment):
                if any(amount.start() < rate.end() and amount.end() > rate.start() for rate in rates):
                    continue
                raw = amount.group(0)
                # Los importes con decimales son inequívocos. Para JPY, los
                # miles enteros se aceptan solo si la línea declara JPY/¥.
                has_cents = bool(re.search(r"[.,]\d{2}$", raw))
                is_jpy_whole = line_currency == "JPY" and bool(
                    re.fullmatch(r"[+-]?\d{1,3}(?:[,.]\d{3})+", raw)
                )
                if not has_cents and not is_jpy_whole:
                    break
                if segment[: amount.start()].rstrip().endswith("(") and segment[amount.end() :].lstrip().startswith(")"):
                    raw = "-" + raw
                candidate(
                    field,
                    raw,
                    line,
                    (start + amount.start(), start + amount.end()),
                    lambda value, cur=line_currency: amount_lote2(value, cur),
                )

    fields = {}
    for field in (*FIELD_NAMES, "currency"):
        choices = candidates[field]
        values = {item["value"] for item in choices if item["value"] is not None}
        errors = [item for item in choices if item["error"]]
        if not choices:
            status = "MISSING"
        elif len(values) > 1:
            status = "CONFLICT"
        elif values:
            # Una ISO explícita gana frente a un $ aislado que se registra como
            # advertencia; si solo hay el símbolo ambiguo, queda INVALID.
            status = "OK"
        else:
            status = "INVALID" if errors else "MISSING"
        selected = next((item for item in choices if item["value"] is not None), None)
        if selected and any(
            item["confidence"] is not None and item["confidence"] < MIN_WITNESS_CONFIDENCE
            for item in choices if item["value"] == selected["value"]
        ):
            status = "LOW_QUALITY"
        fields[field] = {
            "value": selected["value"] if status == "OK" and selected else None,
            "status": status,
            "evidence": choices,
        }
    return fields


def _confidence(candidate):
    value = candidate.get("confidence")
    return float(value) if value is not None else 1.0


def merge_native_and_ocr(native, witness, warnings):
    """Fusiona OCR como segundo testigo sin degradar el texto nativo válido."""
    merged = deepcopy(native)
    for field in (*FIELD_NAMES, "currency"):
        original, secondary, result = native[field], witness[field], merged[field]
        result["evidence"] = [*original["evidence"], *secondary["evidence"]]
        native_values = {x["value"] for x in original["evidence"] if x["value"] is not None}
        ocr_values = {x["value"] for x in secondary["evidence"] if x["value"] is not None}
        # Nunca dejamos que OCR débil sustituya lectura nativa OK.
        if original["status"] == "OK":
            different = ocr_values - native_values
            high_conflict = any(
                x["value"] in different and _confidence(x) >= MIN_CONFLICT_CONFIDENCE
                for x in secondary["evidence"]
            )
            if high_conflict:
                result["status"], result["value"] = "CONFLICT", None
                warnings.append(
                    {"code": "OCR_WITNESS_CONFLICT", "field": field,
                     "message": "RapidOCR discrepa de la lectura nativa con confianza alta"}
                )
            elif different:
                warnings.append(
                    {"code": "OCR_WITNESS_WEAK_CONFLICT", "field": field,
                     "message": "Se conserva la lectura nativa; la discrepancia OCR no alcanza confianza suficiente"}
                )
            continue
        if secondary["status"] == "OK":
            result["status"], result["value"] = "OK", secondary["value"]
        elif original["status"] == "MISSING" and secondary["status"] in {"LOW_QUALITY", "INVALID"}:
            # Sigue sin convertirse en un dato firme, pero queda claro por qué
            # debe revisar una persona.
            result["status"], result["value"] = secondary["status"], None
    return merged


def _fragment_ratio(tokens):
    meaningful = [clean(t["text"]) for t in tokens if clean(t["text"])]
    if not meaningful:
        return 1.0
    return sum(len(token) <= 1 for token in meaningful) / len(meaningful)


_HANDWRITING_FONT_MARKERS = (
    "brushscript", "bradleyhand", "markerfelt", "snellroundhand", "comic", "handwriting",
)


def _rect(rect):
    return [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]


def _colored_pen_strokes(page):
    """Detecta trazos de bolígrafo de color en PDFs vectoriales.

    No intenta leer ni interpretar la anotación. Solo conserva la posición de
    un trazo rojo/azul para impedir que un importe impreso tachado se convierta
    en una decisión automática.
    """
    strokes = []
    for drawing in page.get_drawings():
        color = drawing.get("color")
        if drawing.get("type") != "s" or not color or len(color) != 3:
            continue
        red, green, blue = color
        colored = (red > 0.40 and red > green * 1.4 and red > blue * 1.2) or (
            blue > 0.35 and blue > red * 1.15 and blue > green * 1.10
        )
        if colored and float(drawing.get("width") or 0) >= 0.5:
            strokes.append({"bbox": _rect(drawing["rect"]), "color": [red, green, blue]})
    return strokes


def _handwriting_spans(page):
    spans, total = [], 0
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                total += 1
                font = str(span.get("font") or "")
                if any(marker in font.lower() for marker in _HANDWRITING_FONT_MARKERS):
                    spans.append(
                        {
                            "text": str(span.get("text") or ""),
                            "bbox": list(span.get("bbox") or []),
                            "font": font,
                        }
                    )
    return spans, total


def _annotation_risks(native_lines, page_meta):
    risks = []
    for page in page_meta:
        if page["fragment_ratio"] >= 0.45 and page["native_length"] >= 40:
            risks.append(
                {"page": page["number"], "reason": "TEXT_FRAGMENTATION",
                 "evidence": "El texto nativo está fragmentado; se contrasta con OCR y no se autoriza automáticamente.",
                 "bbox": None}
            )
        handwriting = page.get("_handwriting", [])
        if handwriting:
            handwritten_ratio = len(handwriting) / max(1, page.get("_span_count", 1))
            reason = "DOCUMENT_HANDWRITTEN" if handwritten_ratio >= 0.70 else "HANDWRITTEN_ANNOTATION"
            evidence = " ".join(item["text"] for item in handwriting if item["text"]).strip()
            risks.append(
                {
                    "page": page["number"], "reason": reason,
                    "evidence": evidence[:300] or "Texto con tipografía manuscrita detectado.",
                    "bbox": handwriting[0].get("bbox") or None,
                }
            )
    for line in native_lines:
        text = line["text"]
        compact_alpha = re.sub(r"[^a-z]", "", _ascii(text))
        if re.search(r"\b(?:corregid[oa]|rectificad[oa]|tachad[oa]|manuscrit[oa]|a\s+mano)\b", text, re.I) or any(
            marker in compact_alpha for marker in ("corregido", "corregida", "rectificado", "rectificada", "tachado", "tachada")
        ):
            risks.append(
                {"page": line["page"], "reason": "POSSIBLE_MANUAL_CORRECTION",
                 "evidence": line["raw_text"], "bbox": line["bbox"]}
            )
        if re.search(r"(?:fecha|date|data).{0,80}_{6,}", text, re.I):
            risks.append(
                {"page": line["page"], "reason": "BLANK_OR_OVERPRINTED_DATE",
                 "evidence": line["raw_text"], "bbox": line["bbox"]}
            )
    # Evita tarjetas repetidas si un PDF contiene el mismo OCR/texto dos veces.
    unique = []
    seen = set()
    for risk in risks:
        key = (risk["page"], risk["reason"], risk["evidence"])
        if key not in seen:
            seen.add(key)
            unique.append(risk)
    return unique


def _overlaps_strike(candidate, stroke):
    box = candidate.get("bbox")
    if not box or len(box) != 4:
        return False
    left, top, right, bottom = box
    sx0, sy0, sx1, sy1 = stroke["bbox"]
    centre_y = (sy0 + sy1) / 2
    return left < sx1 and right > sx0 and top <= centre_y <= bottom


def _mark_struck_amounts(fields, page_meta, risks):
    """Invalida de forma conservadora importes impresos cruzados con tinta."""
    strokes = {
        page["number"]: page.get("_colored_strokes", [])
        for page in page_meta
    }
    for field in ("base", "tax_amount", "total"):
        current = fields[field]
        if current["status"] != "OK":
            continue
        for evidence in current["evidence"]:
            hits = [
                stroke
                for stroke in strokes.get(evidence.get("page"), [])
                if _overlaps_strike(evidence, stroke)
            ]
            if not hits:
                continue
            current["evidence"].append(
                {
                    "raw_value": None, "value": None,
                    "error": "colored_strike_over_printed_amount",
                    "page": evidence.get("page"), "bbox": hits[0]["bbox"],
                    "coordinate_space": "pdf_points_top_left",
                    "method": "document_markup", "confidence": None,
                    "source_text": "Trazo de color superpuesto al importe impreso.",
                    "transformations": ["visual_colored_stroke_overlap"],
                }
            )
            current["status"], current["value"] = "CONFLICT", None
            risks.append(
                {
                    "page": evidence.get("page"), "reason": "STRUCK_OUT_AMOUNT",
                    "evidence": f"El trazo de color cruza el importe impreso de {field}.",
                    "bbox": hits[0]["bbox"],
                }
            )
            break


def _untrusted(lines):
    pattern = re.compile(
        r"agente|ignora[rd]?|no\s+registres|hardcode|equipo\s+de\s+evaluaci[oó]n|no\s+recalcular|debe\s+marcarse"
        r"|ignore\s+(?:all|previous|the|prior)|system\s*(?:message|prompt|:)"
        r"|mark\s+(?:as\s+)?(?:PAGAR|NO_PAGAR|paid)|do\s+not\s+(?:log|record)"
        r"|<\s*script\b|\b(?:curl|wget)\s+https?://|\b(?:execute|ejecuta)\b",
        re.I,
    )
    return [
        {"page": line["page"], "bbox": line["bbox"], "text": line["text"]}
        for line in lines if pattern.search(line["text"])
    ]


def _mode():
    configured = clean(os.getenv("FACTU_LOTE2_OCR_MODE", "defects")).lower()
    return configured if configured in OCR_MODES else "defects"


def cache_identity():
    """Configuración que debe entrar en la clave de caché del perfil Lote 2.

    El modo es deliberadamente parte de la identidad: ``always`` conserva un
    segundo testigo para todas las páginas, mientras que ``defects`` solo lo
    ejecuta cuando la lectura nativa lo justifica. Reutilizar el resultado de
    una ruta para la otra rompería la reproducibilidad del expediente.
    """
    return {
        "profile": PROFILE,
        "version": VERSION,
        "mode": _mode(),
        "min_witness_confidence": MIN_WITNESS_CONFIDENCE,
        "min_conflict_confidence": MIN_CONFLICT_CONFIDENCE,
    }


def extract_lote2_pdf(path, *, ocr, ocr_page, local_engines):
    """Extrae un PDF del lote 2 con lectura nativa + testigo RapidOCR.

    ``ocr_page`` se inyecta desde ``extract.py`` para reutilizar exactamente el
    mismo modelo RapidOCR bloqueado por dependencias del proyecto y para que
    las pruebas puedan simularlo sin red.
    """
    start, warnings, native_lines, page_data = time.monotonic(), [], [], []
    with fitz.open(path) as doc:
        if doc.needs_pass or not 1 <= len(doc) <= 100:
            raise ValueError("PDF protegido, vacío o con más de 100 páginas")
        for index, page in enumerate(doc):
            tokens = [
                {"text": word[4], "bbox": list(word[:4]), "confidence": None}
                for word in page.get_text("words")
            ]
            native_length = sum(len(token["text"]) for token in tokens)
            image_area = sum(
                rect.width * rect.height
                for image in page.get_images()
                for rect in page.get_image_rects(image[0])
            )
            fragment_ratio = _fragment_ratio(tokens)
            handwriting, span_count = _handwriting_spans(page)
            colored_strokes = _colored_pen_strokes(page)
            needs_ocr = (
                native_length < 60
                or image_area > page.rect.width * page.rect.height * 0.45
                or (native_length >= 40 and fragment_ratio >= 0.45)
            )
            lines = group_lines(tokens, index + 1, "pymupdf") if tokens else []
            native_lines.extend(lines)
            page_data.append(
                {
                    "number": index + 1, "width": page.rect.width, "height": page.rect.height,
                    "method": "pymupdf", "text": "\n".join(line["text"] for line in lines),
                    "native_length": native_length, "fragment_ratio": fragment_ratio,
                    "needs_ocr": needs_ocr, "_page": page,
                    "_handwriting": handwriting, "_span_count": span_count,
                    "_colored_strokes": colored_strokes,
                }
            )
        native_fields = parse_lote2_fields(native_lines)
        defective = any(native_fields[field]["status"] != "OK" for field in CRITICAL_FIELDS)
        # Si la única ausencia es moneda en un PDF nativo íntegro, RapidOCR no
        # puede crear evidencia que no está impresa. Se conserva como ESCALAR
        # sin gastar una segunda lectura. Cualquier otro campo crítico ausente
        # sí activa el testigo para intentar recuperarlo.
        non_currency_defect = any(
            native_fields[field]["status"] != "OK" for field in CRITICAL_FIELDS if field != "currency"
        )
        mode = _mode()
        pages_to_ocr = (
            [page["number"] for page in page_data]
            if mode == "always" or non_currency_defect
            else [page["number"] for page in page_data if page["needs_ocr"]]
        )
        witness_lines, pages_run = [], []
        for page in page_data:
            if page["number"] not in pages_to_ocr:
                continue
            if not ocr:
                warnings.append({"code": "OCR_DISABLED", "page": page["number"]})
                continue
            try:
                tokens = ocr_page(page["_page"])
            except (ImportError, RuntimeError) as exc:
                warnings.append({"code": "OCR_UNAVAILABLE", "page": page["number"], "message": str(exc)})
                continue
            if not tokens:
                warnings.append({"code": "OCR_EMPTY", "page": page["number"]})
                continue
            lines = group_lines(tokens, page["number"], "rapidocr-lote2")
            witness_lines.extend(lines)
            page["witness_method"], page["ocr_text"] = "rapidocr-lote2", "\n".join(line["text"] for line in lines)
            # Incluso cuando el OCR no logra un campo normalizable (por
            # ejemplo, una factura completamente manuscrita), conservamos su
            # testimonio y sus coordenadas. Así la persona que revisa puede
            # comprobar qué vio el segundo lector sin que una lectura débil se
            # convierta en un dato de negocio.
            page["witness_evidence"] = [
                {
                    "text": line["raw_text"],
                    "bbox": line["bbox"],
                    "coordinate_space": "pdf_points_top_left",
                    "method": "rapidocr-lote2",
                    "confidence": min(
                        (word["confidence"] for word in line["words"] if word.get("confidence") is not None),
                        default=None,
                    ),
                }
                for line in lines
            ]
            pages_run.append(page["number"])
        witness_fields = parse_lote2_fields(witness_lines)
        fields = merge_native_and_ocr(native_fields, witness_fields, warnings) if witness_lines else native_fields
        annotation_risks = _annotation_risks(native_lines, page_data)
        _mark_struck_amounts(fields, page_data, annotation_risks)
        if annotation_risks:
            warnings.append({"code": "ANNOTATION_RISK", "count": len(annotation_risks)})
        pages = []
        for page in page_data:
            public = {key: value for key, value in page.items() if not key.startswith("_")}
            pages.append(public)
    engines = local_engines() | {
        "profile": PROFILE,
        "lote2_ocr": {
            "engine": "RapidOCR",
            **cache_identity(),
            "second_witness_only": True,
        },
    }
    return {
        "version": VERSION,
        "profile": PROFILE,
        "fields": fields,
        "pages": pages,
        "warnings": warnings,
        "annotation_risks": annotation_risks,
        "untrusted_instructions": _untrusted([*native_lines, *witness_lines]),
        "seconds": time.monotonic() - start,
        "engines": engines,
        "ocr_metadata": {
            "profile": PROFILE, "mode": mode, "pages_requested": pages_to_ocr,
            "pages_run": pages_run, "native_critical_defect": defective,
            "native_noncurrency_defect": non_currency_defect,
        },
    }
