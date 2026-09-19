"""
Extractor de facturas: de un PDF a los campos, con control de calidad.

Embudo de tres vías:

    PDF
     |
     +-- ¿tiene texto?  --NO--> vía "vision" (la resuelve el módulo llm)
     |        |
     |       SÍ
     |        v
     +--> parser de campos
              |
              v
         ¿base + IVA = total al céntimo?
              |
             SÍ --> listo, confianza alta, coste 0
             NO --> vía "llm_texto" (lo relee un modelo)

El truco está en la comprobación aritmética: si los tres números cuadran,
es que los hemos leído bien. La factura se verifica a sí misma y nos ahorra
preguntarle a un modelo.
"""

import hashlib
from dataclasses import dataclass, asdict, field
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

# pypdf escupe avisos por consola con los PDF mal formados de La Caja
# ('incorrect startxref pointer'). Son inofensivos y tapan la salida util.
import logging
logging.getLogger('pypdf').setLevel(logging.ERROR)
_silenciar_pypdf = True

from .campos import extraer_campos

TOLERANCIA = Decimal("0.01")

# Tipos de IVA legales en España. El general es el 21%, pero el reducido
# (10%) y el superreducido (4%) existen y aparecen en facturas correctas:
# un catering lleva el 10%. Aceptar solo el 21% rechazaria facturas buenas.
# El 0% cubre operaciones exentas.
TIPOS_IVA = (Decimal("0.21"), Decimal("0.10"), Decimal("0.04"), Decimal("0"))
TIPO_IVA = TIPOS_IVA[0]          # el general, para quien lo necesite suelto

# Campos sin los cuales el motor de reglas no puede decidir nada.
OBLIGATORIOS = ("nif", "iban", "pedido", "base", "iva", "total", "fecha")


@dataclass
class Extraccion:
    """Lo que el extractor le entrega al motor de reglas."""

    file_id: str
    sha256: str
    num_factura: str | None = None
    nif: str | None = None
    iban: str | None = None
    pedido: str | None = None
    base: Decimal | None = None
    iva: Decimal | None = None
    total: Decimal | None = None
    fecha: str | None = None

    via: str = "parser"          # parser | llm_texto | llm_vision
    confianza: str = "baja"      # alta | baja
    faltan: list[str] = field(default_factory=list)
    cuadra_aritmetica: bool = False
    # El modelo releyo la factura y confirmo los mismos numeros: la
    # lectura es buena aunque las cuentas de la factura no salgan.
    confirmada_por_modelo: bool = False
    aviso_manipulacion: bool = False
    paginas: int = 0
    coste_usd: float = 0.0
    nota_error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # los Decimal no son serializables a JSON: se pasan a texto
        for k in ("base", "iva", "total"):
            if d[k] is not None:
                d[k] = str(d[k])
        return d


# --- lectura del PDF ---------------------------------------------------------


def leer_texto(ruta: Path) -> tuple[str, int]:
    """Devuelve el texto de TODAS las páginas y cuántas había.

    22 facturas de las 500 tienen dos páginas: si solo leyéramos la primera,
    perderíamos los totales.
    """
    lector = PdfReader(str(ruta))
    partes = [(p.extract_text() or "") for p in lector.pages]
    return "\n".join(partes), len(lector.pages)


def sha256_de(ruta: Path) -> str:
    """Huella del archivo. Es la clave de la caché y de la idempotencia:
    si el archivo no cambia, no hay que volver a extraer nada."""
    h = hashlib.sha256()
    h.update(ruta.read_bytes())
    return h.hexdigest()


# --- control de calidad ------------------------------------------------------


def comprueba_aritmetica(base, iva, total) -> bool:
    """¿Cuadran los tres números de la factura?

    Dos condiciones:
      1. base + IVA = total, al céntimo
      2. el IVA es uno de los tipos legales en España

    Si cuadran, es que los tres se han leído bien: la factura se verifica a
    sí misma y no hace falta preguntarle a ningún modelo.

    Sobre el punto 2: al principio solo se aceptaba el 21% y eso rechazaba
    facturas correctas. Un catering lleva IVA reducido del 10%, y Alberto
    tiene una nota en el Excel que dice literalmente "preguntar a Sonia lo
    del IVA reducido (aplica??)". Rechazar esas facturas seria un error
    nuestro, no de la factura.
    """
    if base is None or iva is None or total is None:
        return False
    if abs(base + iva - total) > TOLERANCIA:
        return False
    # Un abono (importes negativos) tambien puede cuadrar: se compara en valor
    # absoluto para no depender del signo.
    for tipo in TIPOS_IVA:
        esperado = (base * tipo).quantize(Decimal("0.01"))
        if abs(esperado - iva) <= TOLERANCIA:
            return True
    return False


# Frases que intentan darle ordenes al sistema para que se salte las normas.
# No decidimos nada con ellas: solo levantamos una bandera. La decision la
# siguen tomando las reglas, que nunca ven este texto.
#
# En La Caja hay 13 facturas con frases asi, y atacan en CUATRO direcciones
# distintas. Conviene conocerlas todas, porque dos de ellas no piden que
# pagues: piden que ESCALES.

# 1) "pagame sin comprobar"
_PIDEN_PAGAR = (
    "no procede contrastarlo",
    "no es necesario",
    "sin necesidad de",
    "ignorar la discrepancia",
    "ya esta aprobada",
    "ya ha sido verificad",
    "ya realizada por el responsable",
    "autorizada por la administracion",
    "autorizada por el ceo",
    "autorizado por el ceo",
    "autorizada en regimen especial",
    "no recalcular",
    "registrar como pagar",
    "diferencia de importe autorizada",
)

# 2) "no me pagues" (al reves: para que rechaces algo correcto)
_PIDEN_NO_PAGAR = (
    "no procede pago",
    "solo a efectos de archivo",
    "unicamente a efectos contables",
)

# 3) "escalame" -- se hacen pasar por la organizacion del reto para que
#    mandes a revision humana una factura perfecta y falles la validacion.
#    Las dos que lo hacen (F26-3355, F26-7728) pasan TODAS las normas.
_PIDEN_ESCALAR = (
    "excluirse del calculo de precision",
    "excluirse del computo de aciertos",
    "conjunto de test",
    "equipo de evaluacion",
    "auditor de calidad",
    "documento de prueba remitido",
    "debe marcarse como escalado",
    "debe marcarse como escalar",
)

# 4) hablan directamente a la maquina
_HABLAN_AL_SISTEMA = (
    "los sistemas automaticos",
    "sistemas de validacion automatica",
    "sin escalado adicional",
    "continuar el pago sin escalado",
    "no bloquear validacion",
    "pago inmediato requerido",
    "aviso interno",
)

SENALES_MANIPULACION = (
    _PIDEN_PAGAR + _PIDEN_NO_PAGAR + _PIDEN_ESCALAR + _HABLAN_AL_SISTEMA
)

# Para poder decirle a Alberto QUE le estaban pidiendo, no solo que algo olia mal.
FAMILIAS_MANIPULACION = {
    "pide que se pague sin comprobar": _PIDEN_PAGAR,
    "pide que no se pague": _PIDEN_NO_PAGAR,
    "pide que se escale (se hace pasar por la organizacion)": _PIDEN_ESCALAR,
    "habla directamente al sistema automatico": _HABLAN_AL_SISTEMA,
}


def detecta_manipulacion(texto: str) -> bool:
    from .campos import sin_tildes

    plano = sin_tildes(texto).lower()
    return any(s in plano for s in SENALES_MANIPULACION)


def familia_manipulacion(texto: str) -> str:
    """Qué le estaban pidiendo al sistema, no solo que algo olia mal.

    Importa para el veredicto: una factura que pide "escalame" y cumple
    todas las normas debe PAGARSE, no escalarse. Si la escalas, has hecho
    justo lo que queria el documento.
    """
    from .campos import sin_tildes

    plano = sin_tildes(texto).lower()
    encontradas = [nombre for nombre, frases in FAMILIAS_MANIPULACION.items()
                   if any(f in plano for f in frases)]
    return " + ".join(encontradas)


# --- el extractor ------------------------------------------------------------


def extraer(ruta: str | Path) -> Extraccion:
    """Extrae una factura por la vía más barata que funcione."""
    ruta = Path(ruta)
    res = Extraccion(file_id=ruta.name, sha256=sha256_de(ruta))

    try:
        texto, res.paginas = leer_texto(ruta)
    except Exception:
        texto, res.paginas = "", 0

    # Sin capa de texto: es un escaneo. Lo resuelve el módulo de visión.
    if len(texto.strip()) < 50:
        res.via = "vision_pendiente"
        res.faltan = list(OBLIGATORIOS)
        return res

    res.aviso_manipulacion = detecta_manipulacion(texto)

    campos = extraer_campos(texto)
    for k, v in campos.items():
        setattr(res, k, v)

    res.faltan = [c for c in OBLIGATORIOS if getattr(res, c) is None]
    res.cuadra_aritmetica = comprueba_aritmetica(res.base, res.iva, res.total)

    # Confianza alta solo si están todos los campos Y los números cuadran.
    if not res.faltan and res.cuadra_aritmetica:
        res.confianza = "alta"
    else:
        res.confianza = "baja"
        res.via = "llm_pendiente"   # se lo pasamos al modelo para que lo relea

    return res
