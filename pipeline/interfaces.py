"""Contratos entre modulos (P1-P4).

Este archivo es la unica fuente de verdad sobre que se intercambia.
Los modulos NO se importan entre si: solo importan este fichero y los
llama `main.py`. Asi cada persona puede implementar su archivo sin esperar.

Seguridad: el LLM nunca ve el PDF ni su texto crudo. Solo puede recibir
`CamposExtraidos` (campos estructurados + texto libre YA etiquetado).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Versiones de artefactos (P4 las copia a la traza)
# ---------------------------------------------------------------------------

VERSION_NORMA = "norma-v3-esqueleto"
VERSION_ERP = "ERP Miralmar 2.3.1 (2009)"
VERSION_MANUAL = "MANUAL_ERP_2009.md"


def ahora_iso() -> str:
    """Timestamp UTC en ISO-8601, para cola y trazas."""
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
# P1 - EXTRACCION
# ===========================================================================


@dataclass
class CampoTextoLibre:
    """Fragmento de texto no estructurado extraido del PDF.

    `es_texto_libre=True` avisa a quien consuma el campo (reglas o LLM)
    de que NO es un dato canonico. Si hay indicios de prompt injection,
    se marca `sospecha_inyeccion` y NO se interpreta aqui: solo se senala.
    """

    nombre: str
    valor: str
    es_texto_libre: bool = True
    sospecha_inyeccion: bool = False


@dataclass
class SenalesRiesgo:
    """Alertas de integridad del documento. P1 detecta; no decide."""

    parece_manipulado: bool = False
    indicios_inyeccion: bool = False
    detalle: str = ""


@dataclass
class CamposExtraidos:
    """Salida de P1. Entrada de P2 y P3.

    Recibe:  ruta de un PDF + file_id.
    Devuelve: este dataclass. Nunca incluye texto crudo de pagina.
    """

    file_id: str
    proveedor: Optional[str] = None
    nif_proveedor: Optional[str] = None
    importe: Optional[float] = None
    iva: Optional[float] = None
    fecha: Optional[str] = None  # YYYY-MM-DD cuando se sepa parsear
    numero_factura: Optional[str] = None
    # Clave de conciliacion con el ERP (Norma_Pagos_v3, regla 2). Todas las
    # facturas reales lo imprimen como "Pedido: PO-2026-XXXX". Sin esto, P3
    # no puede cruzar contra los asientos del bridge. Anadido por P3.
    pedido: Optional[str] = None
    campos_texto_libre: list[CampoTextoLibre] = field(default_factory=list)
    tiene_capa_texto: bool = True
    uso_ocr: bool = False
    confianza_ocr: Optional[float] = None  # 0.0-1.0; None si no hubo OCR
    senales_riesgo: SenalesRiesgo = field(default_factory=SenalesRiesgo)
    errores_extraccion: list[str] = field(default_factory=list)


def extraer_campos(ruta_pdf: Path, file_id: str) -> CamposExtraidos:
    """INTERFAZ P1.

    Recibe:
        ruta_pdf: fichero PDF a leer.
        file_id: identificador estable (nombre de archivo de La Caja).

    Devuelve:
        CamposExtraidos con proveedor, importe, IVA, fecha, n. factura
        y campos de texto libre etiquetados. Incluye confianza OCR y
        senales de manipulacion/inyeccion sin intentar "limpiar" el texto.

    Implementacion: `pipeline.extraccion.extraer_campos`.
    """
    raise NotImplementedError("Contrato: implementar en extraccion.py")


# ===========================================================================
# P2 - REGLAS + EXCEL
# ===========================================================================


class DecisionParcialTipo(str, Enum):
    """Lo que P2 puede afirmar sin ERP ni revisor humano."""

    PAGAR = "PAGAR"
    NO_PAGAR = "NO_PAGAR"
    INDETERMINADO = "INDETERMINADO"


@dataclass
class DecisionParcial:
    """Salida de P2. Logica determinista (Excel + normas). Sin LLM."""

    file_id: str
    decision: DecisionParcialTipo
    razonamiento: str
    confianza: float  # 0.0-1.0
    # Si decision=INDETERMINADO, que haria falta para cerrar.
    que_falta: list[str] = field(default_factory=list)
    proveedor_en_excel: Optional[bool] = None
    coincidencias_excel: dict[str, Any] = field(default_factory=dict)


def aplicar_reglas(
    campos: CamposExtraidos,
    ruta_excel: Path,
) -> DecisionParcial:
    """INTERFAZ P2.

    Recibe:
        campos: salida estructurada de P1 (nunca el PDF).
        ruta_excel: proveedores.xlsx (u hoja equivalente).

    Devuelve:
        DecisionParcial PAGAR / NO_PAGAR / INDETERMINADO, con razonamiento
        y confianza. Si es INDETERMINADO, `que_falta` debe ser explicito.

    Implementacion: `pipeline.reglas.aplicar_reglas`.
    """
    raise NotImplementedError("Contrato: implementar en reglas.py")


# ===========================================================================
# P3 - ERP + ESTADO
# ===========================================================================


class EstadoProceso(str, Enum):
    """Maquina de estados persistente por factura (cola)."""

    PENDIENTE = "pendiente"
    PROCESANDO = "procesando"
    PENDIENTE_PREGUNTA = "pendiente_pregunta"
    RESPUESTA = "respuesta"
    DECIDIR = "decidir"
    HECHO = "hecho"
    ERROR = "error"


@dataclass
class ConsultaERP:
    """Una llamada al bridge (para traza). El stub no habla HTTP aun."""

    recurso: str
    parametros: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    codigo_error: Optional[str] = None
    timestamp: str = field(default_factory=ahora_iso)


@dataclass
class ResultadoERP:
    """Respuesta normalizada del ERP de 2009 (tras parsear XML)."""

    file_id: str
    asiento_id: Optional[str] = None
    proveedor: Optional[str] = None
    nif: Optional[str] = None
    pedido: Optional[str] = None
    importe: Optional[float] = None
    estado_asiento: Optional[str] = None  # PENDIENTE | PAGADA
    encontrado: bool = False
    consultas: list[ConsultaERP] = field(default_factory=list)
    notas: str = ""


@dataclass
class InfoDuplicado:
    """Comprobacion de idempotencia / duplicados antes de procesar."""

    file_id: str
    es_duplicado: bool
    file_id_original: Optional[str] = None
    motivo: str = ""


@dataclass
class RegistroEstado:
    """Snapshot persistido en estado/{file_id}.json."""

    file_id: str
    estado: EstadoProceso
    intentos: int = 0
    ultimo_error: Optional[str] = None
    timestamps: dict[str, str] = field(default_factory=dict)
    # Hash o firma ligera para idempotencia (P3 lo rellena).
    firma: Optional[str] = None


def verificar_duplicado(file_id: str, directorio_estado: Path) -> InfoDuplicado:
    """INTERFAZ P3 (antes de procesar).

    Recibe:
        file_id y la carpeta de estado persistente.

    Devuelve:
        InfoDuplicado. Si ya esta en HECHO (o procesandose con la misma
        firma), el orquestador no debe volver a extraer.

    Implementacion: `pipeline.erp_estado.verificar_duplicado`.
    """
    raise NotImplementedError("Contrato: implementar en erp_estado.py")


def consultar_erp(campos: CamposExtraidos) -> ResultadoERP:
    """INTERFAZ P3 (consulta al bridge segun MANUAL_ERP_2009.md).

    Recibe:
        campos estructurados (proveedor, NIF, importe, fecha, n. factura).

    Devuelve:
        ResultadoERP determinista. Reintentos ORA-00600 / SES-401 son
        responsabilidad de esta funcion, no del LLM.

    Implementacion: `pipeline.erp_estado.consultar_erp`.
    """
    raise NotImplementedError("Contrato: implementar en erp_estado.py")


def verificar_duplicado_contenido(campos: "CamposExtraidos", directorio_estado: Path) -> InfoDuplicado:
    """INTERFAZ P3, ADICIONAL (no estaba en el encargo original).

    Complementa a `verificar_duplicado` (que solo cala el mismo file_id
    reprocesado). Esta cala la MISMA factura llegada con otro nombre de
    archivo (NIF+numero+importe+fecha iguales) -- caso real en La Caja:
    "reimpresion_0712.pdf" / "copia_2026_0518.pdf" son escaneos sin capa
    de texto que huelen a ser el reenvio de una factura ya vista.

    Recibe:
        campos: salida de P1 (necesita nif_proveedor, numero_factura,
            importe y fecha; si falta alguno, no se pronuncia).
        directorio_estado: la misma carpeta de la cola persistente.

    Devuelve:
        InfoDuplicado. Si es_duplicado, el orquestador debe forzar
        ESCALAR (norma 6) en vez de dejar pasar un posible pago doble.

    Implementacion: `pipeline.erp_estado.verificar_duplicado_contenido`.
    """
    raise NotImplementedError("Contrato: implementar en erp_estado.py")


def transicionar_estado(
    file_id: str,
    nuevo_estado: EstadoProceso,
    directorio_estado: Path,
    error: Optional[str] = None,
) -> RegistroEstado:
    """INTERFAZ P3 (cola persistente).

    Recibe:
        file_id, estado destino, carpeta, error opcional.

    Devuelve:
        RegistroEstado actualizado, con timestamps. Cada factura es una
        transaccion: si falla, queda en ERROR y se reejecuta despues.

    Implementacion: `pipeline.erp_estado.transicionar_estado`.
    """
    raise NotImplementedError("Contrato: implementar en erp_estado.py")


# ===========================================================================
# Decision final (orquestador) y P4 - SALIDA
# ===========================================================================


class ResultadoFinal(str, Enum):
    """Valores admitidos en outcomes.jsonl (`result`)."""

    PAGAR = "PAGAR"
    NO_PAGAR = "NO_PAGAR"
    ESCALAR = "ESCALAR"


@dataclass
class Pregunta:
    """Pregunta concreta cuando el sistema no esta seguro al 100 por 100."""

    texto: str
    para_quien: str = "revisor"  # revisor | erp | proveedor
    evidencia: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    """Una linea de outcomes.jsonl. Campos extra VAN EN LA MISMA LINEA."""

    file_id: str
    result: ResultadoFinal
    razonamiento: str
    confianza: float
    preguntas: list[Pregunta] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class Traza:
    """Una linea de trazabilidad.jsonl."""

    file_id: str
    estado: EstadoProceso
    timestamps: dict[str, str]
    evidencia: dict[str, Any]
    versiones: dict[str, str]
    consultas_erp: list[dict[str, Any]] = field(default_factory=list)


def escribir_salidas(
    outcome: Outcome,
    traza: Traza,
    directorio_outputs: Path,
    duplicados_sospechosos: Optional[list[InfoDuplicado]] = None,
) -> None:
    """INTERFAZ P4.

    Recibe:
        Outcome y Traza de UNA factura, carpeta outputs/, y opcionalmente
        duplicados sospechosos acumulados (para la vista de revisor).

    Devuelve:
        None. Efecto: append a outcomes.jsonl y trazabilidad.jsonl, y
        actualizacion de la vista de revisor (ESCALAR, preguntas, duplicados).

    Implementacion: `pipeline.salida.escribir_salidas`.
    """
    raise NotImplementedError("Contrato: implementar en salida.py")
