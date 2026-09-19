"""MODELO_PAGINAS_TEXTO: el modelo como tercer lector también en texto nativo.

Apagado por defecto. Se enciende solo para el lote 2, donde las etiquetas están
en otro idioma y el parser deja campos sin leer aunque la página tenga texto.
"""

import pymupdf as fitz
import pytest

from factu import modelo
from factu.extract import extract_pdf
from test_modelo import LINEAS, USO, finge_modelo


def texto_pdf(path, lineas):
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "\n".join(lineas), fontsize=12)
    doc.save(path)
    doc.close()


@pytest.fixture
def sin_base(tmp_path, monkeypatch):
    monkeypatch.setenv("CF_ACCOUNT_ID", "cuenta")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-de-prueba")
    path = tmp_path / "texto.pdf"
    texto_pdf(path, [l for l in LINEAS if "Base" not in l])
    return path


def test_text_page_never_reaches_the_model_while_the_flag_is_off(sin_base, monkeypatch):
    finge_modelo(monkeypatch, pytest.fail)  # cualquier llamada rompe el test
    extraction = extract_pdf(sin_base)
    assert extraction["fields"]["base"]["status"] == "MISSING"
    assert extraction["engines"]["modelo"]["paginas_texto"] is False
    assert "model_usage" not in extraction


def test_flag_sends_the_text_page_and_the_reading_is_validated(sin_base, monkeypatch):
    monkeypatch.setenv("MODELO_PAGINAS_TEXTO", "1")
    llamadas = []
    finge_modelo(
        monkeypatch,
        {
            "campos": {
                "base": {
                    "raw_value": "100,00",
                    "evidencia": "Base imponible 100,00",
                    "page": 1,
                },
                "total": {
                    "raw_value": "5310,00",
                    "evidencia": "Total a pagar en plazo",
                    "page": 1,
                },
            },
            "uso": USO,
        },
        llamadas,
    )
    extraction = extract_pdf(sin_base)
    assert llamadas and llamadas[0][1] == [1]
    assert extraction["engines"]["modelo"]["paginas_texto"] is True
    assert extraction["model_usage"] == USO

    base = extraction["fields"]["base"]
    assert base["status"] == "OK" and base["value"] == "100.00"
    assert base["evidence"][-1]["method"] == "modelo"

    # El total que el modelo no puede enseñar en su evidencia no se acepta:
    # el parser ya había leído 121,00 y la lectura inferida entra con motivo.
    total = extraction["fields"]["total"]
    assert total["value"] == "121.00"
    assert total["evidence"][-1]["error"].startswith("inferido")


def test_flag_is_part_of_the_extraction_cache_key(monkeypatch):
    monkeypatch.delenv("MODELO_PAGINAS_TEXTO", raising=False)
    apagado = modelo.paginas_texto_activas()
    monkeypatch.setenv("MODELO_PAGINAS_TEXTO", "1")
    assert apagado is False and modelo.paginas_texto_activas() is True
