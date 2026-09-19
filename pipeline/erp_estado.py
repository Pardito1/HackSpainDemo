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
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
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

# --- Cliente del bridge ERP (MANUAL_ERP_2009.md) ---------------------------
_ERP_BASE_URL = "http://127.0.0.1:8009"
_ERP_USUARIO = "alberto"
_ERP_CLAVE = "FACTURAS2009"
_ERP_ENCODING = "iso-8859-1"
_ERP_MAX_REINTENTOS_FALLO = 3   # ante ORA-00600
_ERP_ESPACIADO_MIN = 0.11       # ~9 peticiones/s, bajo el limite de 10/s
_ERP_CACHE_NOMBRE = "_erp_cache.json"

_ultimo_ts_peticion = [0.0]


def _espaciar_peticion() -> None:
    """Throttle client-side para no rozar el limite de 10 peticiones/s."""
    espera = _ERP_ESPACIADO_MIN - (time.monotonic() - _ultimo_ts_peticion[0])
    if espera > 0:
        time.sleep(espera)
    _ultimo_ts_peticion[0] = time.monotonic()


def _parsear_error_xml(cuerpo: bytes) -> tuple[str, str]:
    try:
        raiz = ET.fromstring(cuerpo.decode(_ERP_ENCODING, errors="replace"))
        return raiz.findtext("codigo") or "?", raiz.findtext("mensaje") or ""
    except ET.ParseError:
        return "?", cuerpo.decode(_ERP_ENCODING, errors="replace")


def _peticion_cruda(metodo: str, ruta: str, token: str | None = None, datos: dict | None = None) -> bytes:
    url = _ERP_BASE_URL + ruta
    cuerpo = urllib.parse.urlencode(datos).encode("ascii") if datos else None
    cabeceras = {"X-ERP-Token": token} if token else {}
    peticion = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method=metodo)
    _espaciar_peticion()
    with urllib.request.urlopen(peticion, timeout=10) as resp:
        return resp.read()


def _login() -> str:
    cuerpo = _peticion_cruda("POST", "/erp/login", datos={"usuario": _ERP_USUARIO, "clave": _ERP_CLAVE})
    raiz = ET.fromstring(cuerpo.decode(_ERP_ENCODING))
    token = raiz.findtext("token")
    if not token:
        raise RuntimeError("ERP: login sin token en la respuesta")
    return token


def _get_pagina(pagina: int, token: str, consultas: list[ConsultaERP]) -> tuple[ET.Element, str]:
    """Trae una pagina de asientos. Devuelve (xml, token_vigente).

    Reintenta ORA-00600 (misma consulta), relogin ante SES-401 y respeta
    Retry-After ante ERP-429. El token puede cambiar si hizo falta relogin.
    """
    intentos_fallo = 0
    while True:
        try:
            cuerpo = _peticion_cruda("GET", f"/erp/asientos?pagina={pagina}", token=token)
            consultas.append(ConsultaERP(recurso="/erp/asientos", parametros={"pagina": pagina}, ok=True))
            return ET.fromstring(cuerpo.decode(_ERP_ENCODING)), token
        except urllib.error.HTTPError as exc:
            codigo_erp, mensaje = _parsear_error_xml(exc.read())
            consultas.append(
                ConsultaERP(
                    recurso="/erp/asientos",
                    parametros={"pagina": pagina},
                    ok=False,
                    codigo_error=codigo_erp,
                )
            )
            if exc.code == 401:
                token = _login()
                consultas.append(ConsultaERP(recurso="/erp/login", ok=True))
                continue
            if exc.code == 429:
                time.sleep(float(exc.headers.get("Retry-After", "1")))
                continue
            if exc.code == 500 and intentos_fallo < _ERP_MAX_REINTENTOS_FALLO:
                intentos_fallo += 1
                continue
            raise RuntimeError(f"ERP /erp/asientos?pagina={pagina}: {codigo_erp} {mensaje}") from exc


def _fecha_iso(legacy: str) -> str | None:
    try:
        return datetime.strptime(legacy.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _importe_float(legacy: str) -> float | None:
    try:
        return float(legacy.strip().replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _normalizar_asiento(nodo: ET.Element) -> dict:
    return {
        "id": nodo.findtext("id"),
        "fecha": _fecha_iso(nodo.findtext("fecha") or ""),
        "proveedor": nodo.findtext("proveedor"),
        "nif": nodo.findtext("nif"),
        "pedido": nodo.findtext("pedido"),
        "importe": _importe_float(nodo.findtext("importe") or ""),
        "estado": nodo.findtext("estado"),
    }


def _ruta_cache(directorio_estado: Path) -> Path:
    return directorio_estado / _ERP_CACHE_NOMBRE


def _cache_vacia() -> dict:
    return {
        "sincronizado_en": None,
        "total_paginas": None,
        "paginas_ok": [],
        "paginas_fallidas": {},
        "completo": False,
        "por_pedido": {},
    }


def _volcar_pagina(raiz_pagina: ET.Element, por_pedido: dict[str, dict]) -> None:
    for asiento in raiz_pagina.findall("asientos/asiento"):
        norm = _normalizar_asiento(asiento)
        if norm["pedido"]:
            por_pedido[norm["pedido"]] = norm


def _guardar_cache(ruta_cache: Path, estado: dict) -> None:
    """Escribe la caché tal cual esta AHORA. Se llama tras cada pagina, no
    solo al final, para que una caida a mitad no tire el trabajo previo."""
    ruta_cache.parent.mkdir(parents=True, exist_ok=True)
    estado["sincronizado_en"] = ahora_iso()
    estado["total_pedidos"] = len(estado["por_pedido"])
    ruta_cache.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _sincronizar_erp(
    directorio_estado: Path,
    consultas: list[ConsultaERP],
    forzar: bool = False,
) -> dict[str, dict]:
    """Descarga los asientos y los cachea en local por pedido, pagina a pagina.

    Siguiendo el consejo del propio manual: "descargarse los asientos una
    vez y trabajar en local". Llamadas siguientes leen del fichero mientras
    este `completo`, salvo `forzar=True` (p.ej. lote2 del sabado).

    Resiliencia: la cache se guarda despues de CADA pagina, no solo al
    final. Si una pagina agota reintentos y falla de verdad (no el
    ORA-00600 normal, que ya se resuelve solo), esa pagina se apunta en
    `paginas_fallidas` y se sigue con las demas: un tropiezo en la pagina
    15 no debe dejarnos sin los pedidos de las 25 paginas restantes.
    """
    ruta_cache = _ruta_cache(directorio_estado)
    estado = _cache_vacia()
    if ruta_cache.exists() and not forzar:
        estado = json.loads(ruta_cache.read_text(encoding="utf-8"))
        if estado.get("completo"):
            return estado["por_pedido"]
        # Cache incompleta de una ejecucion anterior: retomamos desde ahi
        # en vez de volver a pedir las paginas que ya teniamos bien.

    paginas_ok = set(estado.get("paginas_ok", []))
    paginas_fallidas: dict[str, str] = dict(estado.get("paginas_fallidas", {}))
    por_pedido: dict[str, dict] = estado.get("por_pedido", {})
    total_paginas = estado.get("total_paginas")

    token = _login()
    consultas.append(ConsultaERP(recurso="/erp/login", ok=True))

    if total_paginas is None:
        raiz, token = _get_pagina(1, token, consultas)
        total_paginas = int(raiz.findtext("meta/paginas") or "1")
        _volcar_pagina(raiz, por_pedido)
        paginas_ok.add(1)
        paginas_fallidas.pop("1", None)
        estado.update(
            total_paginas=total_paginas,
            paginas_ok=sorted(paginas_ok),
            paginas_fallidas=paginas_fallidas,
            por_pedido=por_pedido,
        )
        _guardar_cache(ruta_cache, estado)

    for pagina in range(2, total_paginas + 1):
        if pagina in paginas_ok:
            continue
        try:
            raiz, token = _get_pagina(pagina, token, consultas)
        except RuntimeError as exc:
            # Pagina realmente caida (agoto reintentos de ORA-00600, o
            # algo distinto). No abortamos la sincronizacion entera: se
            # apunta como fallida y se sigue con el resto.
            paginas_fallidas[str(pagina)] = repr(exc)
            estado.update(paginas_fallidas=paginas_fallidas)
            _guardar_cache(ruta_cache, estado)
            continue
        _volcar_pagina(raiz, por_pedido)
        paginas_ok.add(pagina)
        paginas_fallidas.pop(str(pagina), None)
        estado.update(
            paginas_ok=sorted(paginas_ok),
            paginas_fallidas=paginas_fallidas,
            por_pedido=por_pedido,
        )
        _guardar_cache(ruta_cache, estado)

    estado["completo"] = len(paginas_ok) == total_paginas and not paginas_fallidas
    _guardar_cache(ruta_cache, estado)
    return por_pedido


def forzar_resincronizacion_erp(directorio_estado: Path | None = None) -> dict:
    """Tira la cache y vuelve a bajar el ERP entero desde cero.

    Pensada para el lote2 del sabado (el ERP se reinicia con
    `--lote2 erp_export_lote2.csv` y puede traer pedidos NUEVOS o
    ACTUALIZADOS) y para el cambio de dato de La Caja del domingo. Un
    resync normal (sin forzar) solo rellena paginas que faltan; esto
    vuelve a pedir las 26 completas porque un pedido ya conocido puede
    haber cambiado de importe/estado sin que su pagina "falte".

    No se llama por factura: se dispara una vez, a mano, con
    `python3 main.py --resync-erp`.
    """
    directorio_estado = directorio_estado or _DIR_ESTADO_DEFECTO
    por_pedido = _sincronizar_erp(directorio_estado, consultas=[], forzar=True)
    estado_guardado = json.loads(_ruta_cache(directorio_estado).read_text(encoding="utf-8"))
    return {
        "total_paginas": estado_guardado.get("total_paginas"),
        "total_pedidos": len(por_pedido),
        "paginas_fallidas": estado_guardado.get("paginas_fallidas", {}),
        "completo": estado_guardado.get("completo", False),
    }


_RAIZ_REPO = Path(__file__).resolve().parent.parent
_DIR_ESTADO_DEFECTO = _RAIZ_REPO / "estado"


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


def _firma_contenido(campos: CamposExtraidos) -> str | None:
    """Firma de contenido para cazar la misma factura con otro nombre de
    archivo (ej. una "reimpresion" o "copia" escaneada de una ya vista).

    Exige NIF + numero de factura + importe + fecha, los cuatro. Si falta
    alguno, no se firma: acusar un falso duplicado por datos incompletos
    es tan mal error como dejar pasar uno de verdad.
    """
    partes = (campos.nif_proveedor, campos.numero_factura, campos.importe, campos.fecha)
    if any(p is None for p in partes):
        return None
    nif, numero, importe, fecha = partes
    return f"{nif.strip().upper()}|{numero.strip().upper()}|{importe:.2f}|{fecha}"


def verificar_duplicado_contenido(campos: CamposExtraidos, directorio_estado: Path) -> InfoDuplicado:
    """Duplicado por CONTENIDO (NIF+numero+importe+fecha), no por file_id.

    Complementa a `verificar_duplicado`: aquella caza el mismo nombre de
    archivo reprocesado (crash/resume); esta caza la MISMA factura
    presentada con otro nombre (p.ej. "reimpresion_0712.pdf" siendo en
    realidad la copia escaneada de una factura ya decidida). Norma 5:
    nunca pagar dos veces el mismo pedido.

    Reutiliza el campo `firma` de `RegistroEstado` que ya dejo preparado
    el esqueleto: se guarda en el registro propio del file_id en cuanto
    se calcula, para que facturas futuras la encuentren cuando esta
    llegue a HECHO. Solo cuentan como "original" los registros ya HECHO;
    uno en PROCESANDO o ERROR no es una fuente fiable todavia.
    """
    firma = _firma_contenido(campos)
    if firma is None:
        return InfoDuplicado(
            file_id=campos.file_id,
            es_duplicado=False,
            motivo="datos insuficientes (falta NIF, numero, importe o fecha) para comparar por contenido",
        )

    if directorio_estado.exists():
        for ruta in directorio_estado.glob("*.json"):
            if ruta.name.startswith("_"):  # caches/indices internos (p.ej. _erp_cache.json), no registros de factura
                continue
            try:
                otro = json.loads(ruta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if (
                otro.get("file_id") != campos.file_id
                and otro.get("firma") == firma
                and otro.get("estado") == EstadoProceso.HECHO.value
            ):
                return InfoDuplicado(
                    file_id=campos.file_id,
                    es_duplicado=True,
                    file_id_original=otro["file_id"],
                    motivo=f"mismo NIF+numero+importe+fecha que {otro['file_id']} (firma={firma})",
                )

    reg = _leer(campos.file_id, directorio_estado)
    if reg is not None and reg.firma is None:
        reg.firma = firma
        _escribir(reg, directorio_estado)

    return InfoDuplicado(file_id=campos.file_id, es_duplicado=False, motivo="firma nueva, no hay coincidencia")


def verificar_duplicado(file_id: str, directorio_estado: Path) -> InfoDuplicado:
    """Duplicado por MISMO file_id ya terminado (crash/resume). El
    duplicado por contenido (otro nombre de archivo) vive en
    `verificar_duplicado_contenido`, que se llama tras la extraccion.
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
    """Conciliacion real contra el bridge ERP 2009 (MANUAL_ERP_2009.md).

    No conecta una vez por factura: la primera llamada del proceso baja
    y cachea TODOS los asientos (26 paginas) en `estado/_erp_cache.json`;
    las siguientes leen ese fichero. Reintentos ORA-00600, relogin ante
    SES-401 y respeto de Retry-After en ERP-429 viven en `_get_pagina`.
    No se usa LLM para nada de esto: es puro parseo determinista de XML.
    """
    consultas: list[ConsultaERP] = []
    ruta_cache = _ruta_cache(_DIR_ESTADO_DEFECTO)
    try:
        por_pedido = _sincronizar_erp(_DIR_ESTADO_DEFECTO, consultas)
    except Exception as exc:  # bridge caido, timeout, etc.
        return ResultadoERP(
            file_id=campos.file_id,
            encontrado=False,
            consultas=consultas,
            notas=f"ERP no disponible, no se puede conciliar: {exc!r}",
        )

    paginas_fallidas = {}
    if ruta_cache.exists():
        paginas_fallidas = json.loads(ruta_cache.read_text(encoding="utf-8")).get("paginas_fallidas", {})
    aviso_incompleto = (
        f" AVISO: la sincronizacion del ERP esta incompleta (paginas caidas: "
        f"{', '.join(sorted(paginas_fallidas))}); este 'no encontrado' puede "
        "deberse a eso, no a que el pedido no exista. Revisar antes de descartar."
        if paginas_fallidas
        else ""
    )

    pedido = campos.pedido
    if not pedido:
        return ResultadoERP(
            file_id=campos.file_id,
            encontrado=False,
            consultas=consultas,
            notas=(
                "La extraccion no dio numero de pedido; no se puede conciliar "
                f"con el ERP (norma 2: escalar).{aviso_incompleto}"
            ),
        )

    asiento = por_pedido.get(pedido)
    if asiento is None:
        return ResultadoERP(
            file_id=campos.file_id,
            pedido=pedido,
            encontrado=False,
            consultas=consultas,
            notas=f"El pedido {pedido} no consta como asiento en el ERP.{aviso_incompleto}",
        )

    return ResultadoERP(
        file_id=campos.file_id,
        asiento_id=asiento["id"],
        proveedor=asiento["proveedor"],
        nif=asiento["nif"],
        pedido=asiento["pedido"],
        importe=asiento["importe"],
        estado_asiento=asiento["estado"],
        encontrado=True,
        consultas=consultas,
        notas="Conciliado contra la cache local del ERP (ver estado/_erp_cache.json).",
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
