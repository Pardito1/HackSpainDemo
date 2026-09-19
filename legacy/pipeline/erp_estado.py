"""P3 - ERP + ESTADO.

Responsable:
  - Consultar el ERP 2009 segun MANUAL_ERP_2009.md (determinista).
  - Cola persistente por factura en `estado/`.
  - Idempotencia por file_id, reintento tras ERROR, duplicados.

La consulta HTTP real al bridge NO esta en este stub. La persistencia
de estado SI es minima y real, para que main.py pueda reintentar y
saltarse duplicados.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.interfaces import (
    CamposExtraidos,
    ConsultaERP,
    EstadoProceso,
    InfoDuplicado,
    RegistroEstado,
    ResultadoERP,
    ahora_iso,
)

_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def _ruta_estado(file_id: str, directorio_estado: Path) -> Path:
    seguro = _SAFE_ID.sub("_", file_id)
    return directorio_estado / f"{seguro}.json"


def _leer(file_id: str, directorio_estado: Path) -> RegistroEstado | None:
    ruta = _ruta_estado(file_id, directorio_estado)
    if not ruta.exists():
        return None
    bruto = json.loads(ruta.read_text(encoding="utf-8"))
    bruto["estado"] = EstadoProceso(bruto["estado"])
    return RegistroEstado(**bruto)


def _escribir(reg: RegistroEstado, directorio_estado: Path) -> None:
    directorio_estado.mkdir(parents=True, exist_ok=True)
    ruta = _ruta_estado(reg.file_id, directorio_estado)
    payload = {
        "file_id": reg.file_id,
        "estado": reg.estado.value,
        "intentos": reg.intentos,
        "ultimo_error": reg.ultimo_error,
        "timestamps": reg.timestamps,
        "firma": reg.firma,
    }
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def verificar_duplicado(file_id: str, directorio_estado: Path) -> InfoDuplicado:
    """Stub + persistencia real: duplicado si ya esta en HECHO.

    TODO(P3): Ademas del file_id, comparar contra facturas ya procesadas
    por (NIF + numero + importe + fecha) para cazar el mismo documento
    con otro nombre de archivo.
    """
    reg = _leer(file_id, directorio_estado)
    if reg is None:
        return InfoDuplicado(file_id=file_id, es_duplicado=False, motivo="no consta")
    if reg.estado == EstadoProceso.HECHO:
        return InfoDuplicado(
            file_id=file_id,
            es_duplicado=True,
            file_id_original=file_id,
            motivo="ya esta en estado hecho (idempotencia por file_id)",
        )
    return InfoDuplicado(
        file_id=file_id,
        es_duplicado=False,
        motivo=f"existe en estado {reg.estado.value}; se puede reanudar",
    )


def consultar_erp(campos: CamposExtraidos) -> ResultadoERP:
    """Stub P3. No llama al bridge; finge un asiento coherente con el ejemplo.

    TODO(P3): Implementar segun MANUAL_ERP_2009.md:
      - POST /erp/login (usuario=alberto, clave del manual).
      - Token en X-ERP-Token; renovar ante SES-401 (15 min / 300 usos).
      - GET /erp/asientos?pagina=N (20 por pagina) o cachear el volcado.
      - Reintentar la MISMA consulta ante ORA-00600 (HTTP 500).
      - Respetar Retry-After en ERP-429.
      - XML ISO-8859-1; importes 12.874,40 y fechas DD/MM/AAAA.
      - Conciliar proveedor/NIF/importe/pedido con CamposExtraidos.
      - No usar LLM para parsear el XML.
    """
    consultas = [
        ConsultaERP(recurso="/erp/login", ok=True),
        ConsultaERP(
            recurso="/erp/asientos",
            parametros={"pagina": 1, "modo": "stub"},
            ok=True,
        ),
    ]

    if campos.file_id == "factura_001.pdf":
        return ResultadoERP(
            file_id=campos.file_id,
            asiento_id="AS-00412",
            proveedor=campos.proveedor,
            nif=campos.nif_proveedor,
            pedido="PED-4412",
            importe=campos.importe,
            estado_asiento="PENDIENTE",
            encontrado=True,
            consultas=consultas,
            notas="stub: asiento de ejemplo alineado con el manual (AS-00412).",
        )

    if campos.file_id == "factura_002.pdf":
        return ResultadoERP(
            file_id=campos.file_id,
            encontrado=False,
            consultas=consultas,
            notas="stub: no hay asiento para este proveedor ficticio.",
        )

    return ResultadoERP(
        file_id=campos.file_id,
        asiento_id="AS-00999",
        proveedor=campos.proveedor,
        nif=campos.nif_proveedor,
        importe=campos.importe,
        estado_asiento="PENDIENTE",
        encontrado=True,
        consultas=consultas,
        notas="stub: asiento encontrado pero importe/pedido no cerrados al 100 por 100.",
    )


def transicionar_estado(
    file_id: str,
    nuevo_estado: EstadoProceso,
    directorio_estado: Path,
    error: str | None = None,
) -> RegistroEstado:
    """Persiste la cola. Si el destino es ERROR, incrementa intentos.

    TODO(P3): Anadir bloqueo por file_id (un proceso a la vez), TTL de
    `procesando` colgado, y reanudacion desde el ultimo estado al arrancar.
    """
    previo = _leer(file_id, directorio_estado)
    if previo is None:
        previo = RegistroEstado(
            file_id=file_id,
            estado=EstadoProceso.PENDIENTE,
            timestamps={"creado": ahora_iso()},
        )

    previo.estado = nuevo_estado
    previo.timestamps[nuevo_estado.value] = ahora_iso()
    if nuevo_estado == EstadoProceso.ERROR:
        previo.intentos += 1
        previo.ultimo_error = error
    elif nuevo_estado == EstadoProceso.PROCESANDO:
        previo.ultimo_error = None
    else:
        if error:
            previo.ultimo_error = error

    _escribir(previo, directorio_estado)
    return previo
