from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else canonical(value).encode()
    ).hexdigest()


def clean(value) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKC", str(value or ""))
        if unicodedata.category(c) != "Cf"
    ).strip()


def identifier(value) -> str:
    return re.sub(r"\s+", "", clean(value)).upper()


def money(value) -> Decimal:
    """Two decimal locales; reject ambiguous thousands-only strings, never guess."""
    if isinstance(value, (int, float, Decimal)):
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("Importe no finito")
        return result
    s = re.sub(r"EUR|€|\s", "", clean(value), flags=re.I)
    if not re.fullmatch(r"[+-]?[0-9][0-9.,]*", s):
        raise ValueError(f"Importe inválido: {value!r}")
    if "," in s and "." in s:
        decimal, grouping = (",", ".") if s.rfind(",") > s.rfind(".") else (".", ",")
        left, right = s.rsplit(decimal, 1)
        if len(right) != 2 or not re.fullmatch(
            r"[+-]?\d{1,3}(?:" + re.escape(grouping) + r"\d{3})+", left
        ):
            raise ValueError("Separadores ambiguos")
        s = left.replace(grouping, "") + "." + right
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        if s.count(sep) != 1 or len(s.rsplit(sep, 1)[1]) not in (1, 2):
            raise ValueError("Separadores ambiguos")
        s = s.replace(sep, ".")
    try:
        result = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError("Importe inválido") from exc
    if not result.is_finite():
        raise ValueError("Importe no finito")
    return result


MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def invoice_date(value: str) -> str:
    s = clean(value).lower()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    match = re.fullmatch(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", s)
    if match and match[2] in MONTHS:
        return (
            datetime(int(match[3]), MONTHS[match[2]], int(match[1])).date().isoformat()
        )
    raise ValueError("Fecha ilegible o inválida")


def iban_checksum(value: str) -> bool:
    s = identifier(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in s[4:] + s[:4])
    return int(digits) % 97 == 1
