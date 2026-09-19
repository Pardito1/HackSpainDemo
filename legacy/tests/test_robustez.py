"""Pruebas de robustez de P1: que nada tumbe el lote entero.

Un PDF roto, vacio o que ni siquiera es un PDF NO puede parar el proceso de
las otras 499 facturas. Debe devolver CamposExtraidos con el error dentro y
seguir adelante.

    python tests/test_robustez.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.extraccion import extraer_campos
from pipeline.interfaces import CamposExtraidos

CAJA = Path(__file__).resolve().parent.parent / "500-sombras-de-alberto-main"
FACTURAS = CAJA / "facturas"


def _tmp(nombre: str, contenido: bytes) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / nombre
    p.write_bytes(contenido)
    return p


# --- archivos que no deberian existir pero existen ---------------------------


def test_archivo_que_no_existe():
    c = extraer_campos(Path("no_existe_en_ningun_sitio.pdf"), "fantasma.pdf")
    assert isinstance(c, CamposExtraidos)
    assert c.file_id == "fantasma.pdf"
    assert c.errores_extraccion          # tiene que decir que pasa
    assert c.importe is None             # y no inventarse nada


def test_pdf_vacio():
    c = extraer_campos(_tmp("vacio.pdf", b""), "vacio.pdf")
    assert isinstance(c, CamposExtraidos)
    assert c.errores_extraccion
    assert c.importe is None


def test_archivo_que_no_es_pdf():
    c = extraer_campos(_tmp("mentira.pdf", b"esto es un txt disfrazado"),
                       "mentira.pdf")
    assert isinstance(c, CamposExtraidos)
    assert c.importe is None


def test_pdf_truncado():
    # cabecera valida y nada mas: el caso clasico de descarga a medias
    c = extraer_campos(_tmp("roto.pdf", b"%PDF-1.4\n1 0 obj\n<<"), "roto.pdf")
    assert isinstance(c, CamposExtraidos)
    assert c.importe is None


def test_el_file_id_siempre_se_respeta():
    # el file_id de la entrega sale de aqui: no se puede perder ni cambiar
    for nombre in ("factura_1936.pdf", "FA-3388_ofimática.pdf", "raro .pdf"):
        c = extraer_campos(Path("da_igual.pdf"), nombre)
        assert c.file_id == nombre


# --- sobre facturas reales ---------------------------------------------------


def test_idempotencia():
    """Extraer dos veces el mismo PDF da exactamente lo mismo.

    Si esto falla, el JSONL de la entrega cambiaria entre ejecuciones y no
    podriamos defender ninguna decision.
    """
    from dataclasses import asdict

    p = FACTURAS / "2026-01-08_P001.pdf"
    if not p.exists():
        return
    a = asdict(extraer_campos(p, p.name))
    b = asdict(extraer_campos(p, p.name))
    assert a == b


def test_nunca_devuelve_el_texto_crudo():
    """El contrato lo exige: P1 no puede filtrar el texto de la pagina.

    Si el texto crudo llegara a P2, las frases de inyeccion tambien. La
    defensa del sistema depende de que esto se cumpla.
    """
    p = FACTURAS / "factura_1936.pdf"   # la que trae la nota del "CEO"
    if not p.exists():
        return
    c = extraer_campos(p, p.name)
    todo = " ".join(str(x.valor) for x in c.campos_texto_libre).lower()
    assert "ceo" not in todo
    assert "aprobada" not in todo
    # pero SI tiene que avisar de que el documento trae instrucciones
    assert c.senales_riesgo.indicios_inyeccion


def test_la_inyeccion_no_cambia_los_datos():
    """La factura del 'CEO' se lee igual que cualquier otra."""
    p = FACTURAS / "factura_1936.pdf"
    if not p.exists():
        return
    c = extraer_campos(p, p.name)
    assert c.senales_riesgo.indicios_inyeccion      # marcada
    assert c.importe is not None                    # y aun asi leida
    assert c.pedido is not None
    assert c.cuadra_aritmetica                      # sus cuentas cuadran


def test_las_de_dos_paginas_leen_el_total():
    """22 facturas tienen dos paginas y el total esta en la ultima."""
    import logging
    import warnings
    warnings.filterwarnings("ignore")
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    from pypdf import PdfReader

    if not FACTURAS.exists():
        return
    revisadas = 0
    for p in sorted(FACTURAS.glob("*.pdf")):
        try:
            if len(PdfReader(str(p)).pages) < 2:
                continue
        except Exception:
            continue
        c = extraer_campos(p, p.name)
        assert c.importe is not None, f"{p.name}: sin total"
        revisadas += 1
        if revisadas >= 5:
            break
    assert revisadas > 0


if __name__ == "__main__":
    import logging
    import warnings
    warnings.filterwarnings("ignore")
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    fallos = 0
    pruebas = [(n, f) for n, f in sorted(globals().items())
               if n.startswith("test_") and callable(f)]
    for nombre, funcion in pruebas:
        try:
            funcion()
            print(f"  ok    {nombre}")
        except AssertionError as e:
            fallos += 1
            print(f"  FALLA {nombre}  {e}")
        except Exception as e:
            fallos += 1
            print(f"  ERROR {nombre}  {type(e).__name__}: {e}")
    print()
    print(f"  {len(pruebas) - fallos}/{len(pruebas)} pruebas pasan")
    sys.exit(1 if fallos else 0)
