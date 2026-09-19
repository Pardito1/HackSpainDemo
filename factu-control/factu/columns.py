"""Resolve explicit workbook headers; never guess columns from their contents."""
import re
import unicodedata


def normalized(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return re.sub(r"[^a-z0-9]", "", text)


def resolve_columns(sheet, aliases, required):
    header = next(sheet.iter_rows(max_row=1), ())
    columns = {}
    for field, names in aliases.items():
        allowed = {normalized(name) for name in names}
        matches = [i for i, cell in enumerate(header)
                   if cell.data_type != "f" and normalized(cell.value) in allowed]
        if len(matches) > 1:
            raise ValueError(f"{sheet.title}: hay varias columnas para {names[0]}. Conserva una sola para evitar ambigüedades.")
        if matches:
            columns[field] = matches[0]
    if any(field not in columns for field in required):
        names = ", ".join(" / ".join(aliases[field]) for field in required)
        raise ValueError(f"{sheet.title}: se esperan las columnas {names}. Revisa los encabezados antes de continuar.")
    return columns


ORDER_COLUMNS = {"order": ("Pedido",), "supplier_id": ("ProveedorID",),
                 "nif": ("NIF",), "total": ("Importe", "Importe_Total"),
                 "state": ("Estado",), "date": ("Fecha_Pedido",)}
