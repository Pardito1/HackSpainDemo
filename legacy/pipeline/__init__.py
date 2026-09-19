"""Paquete del pipeline de decision de facturas.

Los cuatro modulos (extraccion, reglas, erp_estado, salida) se comunican
solo a traves de `interfaces`. No os importeis unos a otros.
"""

from pipeline.interfaces import (  # noqa: F401
    CamposExtraidos,
    DecisionParcial,
    Outcome,
    ResultadoERP,
    Traza,
)
