"""
Búsqueda de campos en el texto de una factura.

La idea: NO hacemos un parser por plantilla. Hacemos un buscador por CAMPO.
Cada campo tiene una lista de patrones; se prueban en orden y gana el primero
que acierta. Así, si el lote 2 del sábado trae una plantilla nueva que mezcla
etiquetas que ya conocemos, la pillamos sin tocar nada.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

# --- utilidades de texto -----------------------------------------------------


# Caracteres que no se ven pero rompen cualquier patrón.
#
# En La Caja hay dos facturas que esconden el importe asi:
#
#     TOTAL: 2<ZWSP>.<ZWSP>6<ZWSP>3<ZWSP>7<ZWSP>,<ZWSP>8<ZWSP>0
#
# Un humano lee 2.637,80. Un parser ingenuo lee 2. Es ofuscacion
# deliberada, del mismo estilo que las frases escondidas para el modelo.
# Casos reales: FA-4488_transportes.pdf y F26-3011_suministros.pdf.
INVISIBLES = str.maketrans({
    "​": "",   # espacio de ancho cero
    "‌": "",   # no-juntador de ancho cero
    "‍": "",   # juntador de ancho cero
    "⁠": "",   # unidor de palabras
    "﻿": "",   # marca de orden de bytes
    "­": "",   # guion blando
    " ": " ",  # espacio duro -> espacio normal
    " ": " ",  # espacio fino duro
})


def limpia_invisibles(texto: str) -> str:
    """Quita los caracteres que no se ven pero separan cifras."""
    return texto.translate(INVISIBLES)


def sin_tildes(texto: str) -> str:
    """Aplana el texto para que los patrones no dependan de la codificación.

    Hace dos cosas:
      1. quita los caracteres invisibles (ver arriba: son una trampa)
      2. quita las tildes, porque el PDF a veces devuelve 'Ofim?tica'
         en vez de 'Ofimática' segun como se codificara
    """
    nfkd = unicodedata.normalize("NFKD", limpia_invisibles(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _buscar(texto: str, patrones: list[str]) -> str | None:
    """Prueba los patrones en orden y devuelve el primer grupo que capture."""
    for patron in patrones:
        m = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


# --- conversores -------------------------------------------------------------

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def parse_importe(bruto: str | None) -> Decimal | None:
    """Convierte '2.452,27' o '1250.00' o '1.250' en Decimal.

    Usamos Decimal y NO float: con float, 0.1 + 0.2 no da 0.3, y con una
    tolerancia de 0,01 EUR eso nos costaría un veredicto.

    Reglas:
      - Si hay coma, la coma es el decimal y los puntos son miles.
      - Si solo hay punto: 2 decimales -> punto decimal; 3 -> punto de miles.
    """
    if not bruto:
        return None
    s = bruto.strip().replace("EUR", "").replace("€", "").strip()
    s = s.replace(" ", "")
    if not s:
        return None

    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        entera, _, decimal = s.rpartition(".")
        # '1.250' con 3 cifras detrás y algo delante es punto de miles
        if len(decimal) == 3 and entera:
            s = entera.replace(".", "") + decimal
        # si son 2 (o 1) cifras, el punto ya es el decimal: se deja igual

    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_fecha(bruto: str | None) -> str | None:
    """Devuelve la fecha en ISO (AAAA-MM-DD) desde los formatos que aparecen.

    Formatos vistos en las facturas reales:
      08/01/2026        el común
      2026-01-08        ya en ISO
      15 de enero de 2026   escrito en letra
    """
    if not bruto:
        return None
    s = sin_tildes(bruto.strip().lower())

    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        d, mes, a = m.groups()
        return f"{a}-{int(mes):02d}-{int(d):02d}"

    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        a, mes, d = m.groups()
        return f"{a}-{int(mes):02d}-{int(d):02d}"

    m = re.match(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", s)
    if m:
        d, nombre_mes, a = m.groups()
        mes = MESES.get(nombre_mes)
        if mes:
            return f"{a}-{mes:02d}-{int(d):02d}"

    return None


def normaliza_iban(bruto: str | None) -> str | None:
    """Quita espacios y pasa a mayúsculas: 'ES21 0049...' -> 'ES2100490...'."""
    if not bruto:
        return None
    return re.sub(r"\s+", "", bruto).upper()


# --- patrones por campo ------------------------------------------------------
# Cada lista va de lo más específico a lo más general. Gana el primero.

# Un número decimal español o inglés: 12.874,40 / 1250.00 / 458,04
# Sin \s dentro: si permitimos espacios, \s incluye el salto de línea y el
# patrón se traga el importe de la línea siguiente.
# El signo menos es opcional: hay facturas rectificativas (abonos) con
# importes negativos, y si no se captura el signo, un abono de -605 se
# leería como un cobro de 605.
_IMP = r"(-?[\d][\d.,]*[\d]|-?\d)"

# El porcentaje del IVA, que va entre la etiqueta y el importe:
# "IVA (21%): 522,90"  ->  hay que saltarse el 21 y coger el 522,90.
_PCT = r"(?:\s*\(\s*\d+\s*%\s*\))?"

# Prefijo de moneda opcional: el formato ingles escribe "EUR 192.95".
_MON = r"(?:EUR\s*|€\s*)?"

PATRONES = {
    "num_factura": [
        r"Invoice\s*#\s*([A-Z0-9/\-]+)",
        r"FACTURA\s+SIMPLIFICADA\s+N[º°o]?\s*([A-Z0-9/\-]+)",
        r"N[º°o]?\s*de\s*factura\s*:?\s*([A-Z0-9/\-]+)",
        r"REF\s+FACTURA\s*:?\s*([A-Z0-9/\-]+)",
        r"FACTURA\s*N[º°o]?\s*:?\s*([A-Z0-9/\-]+)",
        r"Factura\s*:?\s*([A-Z0-9/\-]+)",
    ],
    "fecha": [
        # primero las etiquetas explicitas, de la mas especifica a la mas
        # general; el ultimo patron es la red de seguridad
        r"Fecha\s+de\s+emisi[oó]n\s*:?\s*(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
        r"Fecha\s+factura\s*:?\s*([\d/\-]{8,10})",
        r"Fecha\s+de\s+(?:emisi[oó]n|factura)\s*:?\s*([\d/\-]{8,10})",
        r"Emitida?\s+e[ln]\s*:?\s*([\d/\-]{8,10})",
        r"Invoice\s+date\s*:?\s*([\d/\-]{8,10})",
        r"\bDate\s*:?\s*([\d/\-]{8,10})",
        r"\bData\s*:?\s*([\d/\-]{8,10})",            # valenciano
        r"FECHA\s*:?\s*([\d/\-]{8,10})",
        r"Fecha\s*:?\s*([\d/\-]{8,10})",
        r"(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
        # Ultimo recurso: la primera fecha del documento. Da igual como se
        # llame la etiqueta, y cubre las que traiga el lote 2. Va la ultima
        # para que cualquier etiqueta conocida tenga prioridad.
        r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
    ],
    "pedido": [
        # El identificador es tan característico que se busca directamente:
        # asi da igual como se llame la etiqueta ("Comanda", "Orden de
        # compra", "Purchase Order"...). Comprobado: ninguna factura de La
        # Caja contiene dos pedidos distintos, asi que no hay ambiguedad.
        r"\b(PO-\d{4}-\d{4})\b",
        r"Pedido\s+asociado\s*:?\s*([A-Z0-9\-]+)",
        r"PEDIDO\s+CLIENTE\s*:?\s*([A-Z0-9\-]+)",
        r"Su\s+pedido\s*:?\s*([A-Z0-9\-]+)",
        r"Ref\.?\s*Pedido\s*:?\s*([A-Z0-9\-]+)",
        r"Orden\s+de\s+compra\s*:?\s*([A-Z0-9\-]+)",
        r"Purchase\s+Order\s*:?\s*([A-Z0-9\-]+)",
        r"Comanda\s*:?\s*([A-Z0-9\-]+)",
        r"\bPO\s*:?\s*([A-Z0-9\-]+)",
        r"Pedido\s*:?\s*([A-Z0-9\-]+)",
    ],
    "nif": [
        # NIF del emisor. OJO: el CIF del cliente (A58231074) NO es este;
        # se borra del texto antes de buscar (ver extraer_campos).
        r"NIF\s*(?:del\s+emisor)?\s*:?\s*([A-Z]\d{8})",
        r"N\.I\.F\.?\s*:?\s*([A-Z]\d{8})",
        r"Ident\w*\.?\s+fiscal\s*:?\s*([A-Z]\d{8})",
        r"Tax\s*ID\s*:?\s*([A-Z]\d{8})",
        r"VAT\s*(?:number)?\s*:?\s*(?:ES)?\s*([A-Z]\d{8})",
        r"CIF\s*:?\s*([A-Z]\d{8})",
        # Ultimo recurso: cualquier identificador fiscal espanol suelto.
        # Una letra y ocho digitos es un patron muy especifico, y el CIF del
        # cliente ya se ha quitado. Asi da igual como se llame la etiqueta:
        # cubre "Ident. fiscal", "Tax ID" y las que traiga el lote 2.
        r"\b([A-Z]\d{8})\b",
    ],
    "iban": [
        r"(?:Cuenta\s+de\s+abono\s*)?\(?IBAN\)?\s*:?\s*(ES\d{2}[\d\s]{18,26})",
        r"\b(ES\d{2}[\d\s]{18,26})",
    ],
    "base": [
        r"Base\s+imponible\s*[.:]*\s*" + _MON + _IMP,
        r"Base\s+imposable\s*[.:]*\s*" + _MON + _IMP,      # valenciano
        r"Importe\s+base\s*[.:]*\s*" + _MON + _IMP,
        r"Importe\s+neto\s*[.:]*\s*" + _MON + _IMP,
        r"Subtotal\s*[.:]*\s*" + _MON + _IMP,
        r"Taxable\s+(?:base|amount)\s*[.:]*\s*" + _MON + _IMP,
        r"BASE\s*[.:]*\s*" + _MON + _IMP,
        r"Base\s*[.:]*\s*" + _MON + _IMP,
    ],
    "iva": [
        r"Cuota\s+IVA" + _PCT + r"\s*[.:]*\s*" + _MON + _IMP,
        r"I\.V\.A\.?" + _PCT + r"\s*[.:]*\s*" + _MON + _IMP,
        r"IVA" + _PCT + r"\s*[.:]*\s*" + _MON + _IMP,
    ],
    "total": [
        r"TOTAL\s+A\s+PAGAR\s*[.:]*\s*" + _MON + _IMP,
        r"IMPORTE\s+TOTAL\s*[.:]*\s*" + _MON + _IMP,
        r"Total\s+factura\s*[.:]*\s*" + _MON + _IMP,
        r"TOTAL\s*[.:]*\s*" + _MON + _IMP,
    ],
}

# CIF del cliente: sale en todas las facturas y NO debe confundirse con el NIF
# del proveedor. Lo tenemos localizado para poder descartarlo.
CIF_CLIENTE = "A58231074"


def extraer_campos(texto: str) -> dict:
    """Saca los 8 campos del texto plano de una factura.

    Devuelve siempre las mismas claves; el valor es None si no se encontró.
    """
    plano = sin_tildes(texto)

    # El NIF del cliente aparece siempre; lo quitamos para no capturarlo
    # por error como NIF del proveedor.
    plano_sin_cliente = plano.replace(CIF_CLIENTE, "")

    crudo = {
        campo: _buscar(plano_sin_cliente if campo == "nif" else plano, patrones)
        for campo, patrones in PATRONES.items()
    }

    return {
        "num_factura": crudo["num_factura"],
        "nif": crudo["nif"].upper() if crudo["nif"] else None,
        "iban": normaliza_iban(crudo["iban"]),
        "pedido": crudo["pedido"],
        "base": parse_importe(crudo["base"]),
        "iva": parse_importe(crudo["iva"]),
        "total": parse_importe(crudo["total"]),
        "fecha": parse_fecha(crudo["fecha"]),
    }
