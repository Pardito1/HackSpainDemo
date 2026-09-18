#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ERP Miralmar · bridge HTTP "AS/400" v2.3.1 (instalado en 2009, no tocar).

Este es el ERP del cliente. Alberto no tiene acceso directo a la base de
datos: tiene ESTO, un bridge HTTP que Sistemas instaló en 2009 y que nadie
se atreve a actualizar. Los asientos contables contra los que hay que
conciliar viven aquí dentro.

Arranca en vuestra máquina (no depende de la wifi del evento):

    python3 alberto_erp.py                # puerto 8009
    python3 alberto_erp.py --puerto 8010  # si el 8009 está ocupado

El sábado, cuando Alberto mande más trabajo, cargad la actualización así:

    python3 alberto_erp.py --lote2 ruta/al/erp_export_lote2.csv

Manual de uso (credenciales, endpoints y códigos de error): MANUAL_ERP_2009.md

`--rapido` quita la latencia artificial (pensado para tests automatizados;
el ERP de verdad no tiene ese flag, lo sabemos).

Solo usa la librería estándar de Python 3.9+.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import secrets
import sys
import threading
import time
import zlib
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

USUARIO = "alberto"
CLAVE = "FACTURAS2009"
PAGINA_TAMANO = 20              # 26 páginas en el lote 1: la paginación se nota
TOKEN_VIGENCIA_SEGUNDOS = 900   # 15 minutos, como las sesiones de la intranet
TOKEN_VIGENCIA_USOS = 300
FALLO_CADA = 10                 # cada 10ª consulta autenticada, ORA-00600: una descarga
                                # completa (27+ consultas) VE el error y debe reintentar
RATE_MAX_POR_SEGUNDO = 10
VERSION = "ERP Miralmar · bridge AS/400 2.3.1 (2009)"

# === BLOQUE DE DATOS (no editar a mano; regenerar con interno/generador/embed_erp.py) ===
_DATOS_ERP = (
    "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"
)
# === FIN BLOQUE DE DATOS ===


def _cargar_asientos_embebidos() -> "list[dict[str, str]]":
    crudo = zlib.decompress(base64.b64decode(_DATOS_ERP)).decode("utf-8")
    return list(csv.DictReader(io.StringIO(crudo)))


def _cargar_asientos_csv(ruta: str) -> "list[dict[str, str]]":
    with open(ruta, "r", encoding="utf-8-sig", newline="") as handle:
        filas = list(csv.DictReader(handle))
    esperadas = {"asiento_id", "fecha_registro", "proveedor_id", "nif", "pedido", "importe_esperado", "estado"}
    if not filas or not esperadas.issubset(filas[0].keys()):
        raise SystemExit(f"ERROR: {ruta} no parece un export del ERP (faltan columnas)")
    return filas


def _fecha_legacy(iso: str) -> str:
    try:
        return datetime.strptime(iso.strip(), "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _importe_legacy(valor: str) -> str:
    try:
        cantidad = float(valor)
    except ValueError:
        return valor
    entero, decimales = f"{cantidad:.2f}".split(".")
    con_miles = ""
    while len(entero) > 3:
        con_miles = "." + entero[-3:] + con_miles
        entero = entero[:-3]
    return entero + con_miles + "," + decimales


def _xml_escape(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xml_asiento(fila: "dict[str, str]") -> str:
    return (
        "    <asiento>\n"
        f"      <id>{_xml_escape(fila['asiento_id'])}</id>\n"
        f"      <fecha>{_fecha_legacy(fila['fecha_registro'])}</fecha>\n"
        f"      <proveedor>{_xml_escape(fila['proveedor_id'])}</proveedor>\n"
        f"      <nif>{_xml_escape(fila['nif'])}</nif>\n"
        f"      <pedido>{_xml_escape(fila['pedido'])}</pedido>\n"
        f"      <importe>{_importe_legacy(fila['importe_esperado'])}</importe>\n"
        f"      <estado>{_xml_escape(fila['estado'])}</estado>\n"
        "    </asiento>\n"
    )


class EstadoERP:
    """Estado compartido del bridge: asientos, sesiones y contadores."""

    def __init__(self, asientos: "list[dict[str, str]]", latencia: float) -> None:
        self.lock = threading.Lock()
        self.asientos = asientos
        self.por_id = {fila["asiento_id"]: fila for fila in asientos}
        self.latencia = latencia
        self.arranque = time.time()
        self.lote2_cargado = False
        self.sesiones: "dict[str, dict[str, float]]" = {}
        self.consultas_autenticadas = 0
        self.ventana = deque()  # timestamps de peticiones recientes (rate limit)

    def cargar_lote2(self, filas: "list[dict[str, str]]") -> "tuple[int, int]":
        nuevos = actualizados = 0
        for fila in filas:
            if fila["asiento_id"] in self.por_id:
                self.por_id[fila["asiento_id"]].update(fila)
                actualizados += 1
            else:
                self.asientos.append(fila)
                self.por_id[fila["asiento_id"]] = fila
                nuevos += 1
        self.lote2_cargado = True
        return nuevos, actualizados

    def crear_sesion(self) -> str:
        token = secrets.token_hex(16)
        self.sesiones[token] = {"caduca": time.time() + TOKEN_VIGENCIA_SEGUNDOS, "usos": 0}
        return token

    def validar_sesion(self, token: "str | None") -> bool:
        if not token or token not in self.sesiones:
            return False
        sesion = self.sesiones[token]
        if time.time() > sesion["caduca"] or sesion["usos"] >= TOKEN_VIGENCIA_USOS:
            del self.sesiones[token]
            return False
        sesion["usos"] += 1
        return True

    def sobre_limite(self) -> bool:
        ahora = time.time()
        self.ventana.append(ahora)
        while self.ventana and ahora - self.ventana[0] > 1.0:
            self.ventana.popleft()
        return len(self.ventana) > RATE_MAX_POR_SEGUNDO

    def toca_fallo(self) -> bool:
        self.consultas_autenticadas += 1
        return self.consultas_autenticadas % FALLO_CADA == 0


ESTADO: "EstadoERP | None" = None


class ManejadorERP(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MiralmarBridge/2.3.1"
    sys_version = ""

    # --- fontanería ---

    def _responder(self, codigo: int, cuerpo: str, tipo: str = "text/xml", extra: "dict[str, str] | None" = None) -> None:
        datos = cuerpo.encode("iso-8859-1", errors="replace")
        self.send_response(codigo)
        self.send_header("Content-Type", f"{tipo}; charset=ISO-8859-1")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("X-ERP-Version", "2.3.1-2009")
        for clave, valor in (extra or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        try:
            self.wfile.write(datos)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error_xml(self, codigo: int, codigo_erp: str, mensaje: str, extra: "dict[str, str] | None" = None) -> None:
        cuerpo = (
            '<?xml version="1.0" encoding="ISO-8859-1"?>\n'
            f"<error>\n  <codigo>{codigo_erp}</codigo>\n  <mensaje>{_xml_escape(mensaje)}</mensaje>\n</error>\n"
        )
        self._responder(codigo, cuerpo, extra=extra)

    def log_message(self, formato: str, *args: object) -> None:
        hora = datetime.now().strftime("%H:%M:%S")
        sys.stdout.write(f"[ERP 2009] {hora} {formato % args}\n")
        sys.stdout.flush()

    def _redirigir(self, destino: str) -> None:
        self.send_response(302)
        self.send_header("Location", destino)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _token(self, consulta: "dict[str, list[str]]") -> "str | None":
        cabecera = self.headers.get("X-ERP-Token")
        if cabecera:
            return cabecera.strip()
        valores = consulta.get("token")
        return valores[0].strip() if valores else None

    def _portazo_comun(self) -> bool:
        """Rate limit + latencia de época. True si ya se respondió."""
        assert ESTADO is not None
        with ESTADO.lock:
            pasado = ESTADO.sobre_limite()
        if pasado:
            self._error_xml(429, "ERP-429", "Demasiadas peticiones. El bridge es de 2009; respete la cola.", extra={"Retry-After": "1"})
            return True
        if ESTADO.latencia:
            time.sleep(ESTADO.latencia)
        return False

    # --- endpoints ---

    def do_POST(self) -> None:  # noqa: N802 (nombre exigido por BaseHTTPRequestHandler)
        assert ESTADO is not None
        url = urlparse(self.path)
        if self._portazo_comun():
            return
        if url.path != "/erp/login":
            self._error_xml(404, "ERP-404", "Recurso no encontrado. Consulte el manual de 2009.")
            return
        longitud = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(longitud).decode("utf-8", errors="replace") if longitud else ""
        campos = parse_qs(cuerpo)
        usuario = (campos.get("usuario") or [""])[0]
        clave = (campos.get("clave") or [""])[0]
        origen_web = (campos.get("origen") or [""])[0] == "web"
        if usuario != USUARIO or clave != CLAVE:
            if origen_web:
                self._redirigir("/?error=1")
                return
            self._error_xml(401, "SES-401", "Credenciales no reconocidas. Ver MANUAL_ERP_2009.md, seccion 2.")
            return
        with ESTADO.lock:
            token = ESTADO.crear_sesion()
        if origen_web:
            self._redirigir(f"/erp/consulta?token={token}")
            return
        cuerpo_xml = (
            '<?xml version="1.0" encoding="ISO-8859-1"?>\n'
            "<sesion>\n"
            f"  <token>{token}</token>\n"
            f"  <caduca_en_segundos>{TOKEN_VIGENCIA_SEGUNDOS}</caduca_en_segundos>\n"
            f"  <usos_maximos>{TOKEN_VIGENCIA_USOS}</usos_maximos>\n"
            "  <aviso>Guarde este token. El bridge no lo repetira.</aviso>\n"
            "</sesion>\n"
        )
        self._responder(200, cuerpo_xml)

    def do_GET(self) -> None:  # noqa: N802
        assert ESTADO is not None
        url = urlparse(self.path)
        consulta = parse_qs(url.query)
        if self._portazo_comun():
            return

        if url.path == "/" or url.path == "/index.html":
            self._portada(error=bool(consulta.get("error")))
            return

        if url.path == "/erp/consulta":
            self._consulta_web(consulta)
            return

        if url.path == "/erp/estado":
            activo = int(time.time() - ESTADO.arranque)
            cuerpo = (
                '<?xml version="1.0" encoding="ISO-8859-1"?>\n'
                "<estado>\n"
                f"  <version>{VERSION}</version>\n"
                f"  <activo_segundos>{activo}</activo_segundos>\n"
                f"  <asientos>{len(ESTADO.asientos)}</asientos>\n"
                f"  <actualizacion_cargada>{'SI' if ESTADO.lote2_cargado else 'NO'}</actualizacion_cargada>\n"
                "  <animo>El sistema lleva 17 anos funcionando. No sera hoy.</animo>\n"
                "</estado>\n"
            )
            self._responder(200, cuerpo)
            return

        if not url.path.startswith("/erp/asientos"):
            self._error_xml(404, "ERP-404", "Recurso no encontrado. Consulte el manual de 2009.")
            return

        with ESTADO.lock:
            autorizado = ESTADO.validar_sesion(self._token(consulta))
        if not autorizado:
            self._error_xml(401, "SES-401", "Sesion no valida o caducada. Identifiquese de nuevo en /erp/login.")
            return
        with ESTADO.lock:
            falla = ESTADO.toca_fallo()
        if falla:
            self._error_xml(500, "ORA-00600", "Error interno del nucleo del bridge. Reintente la peticion. Si persiste, contacte con Mantenimiento (ext. 2009).")
            return

        if url.path.rstrip("/") == "/erp/asientos":
            self._listar_asientos(consulta)
            return
        asiento_id = url.path.rsplit("/", 1)[-1]
        self._detalle_asiento(asiento_id)

    ESTILO_2009 = """<style>body{font-family:Verdana,Arial,sans-serif;font-size:12px;background:#D6D2C4;margin:24px}
.caja{background:#FFFFFF;border:2px outset #808080;padding:14px;max-width:760px}
h1{font-size:15px;color:#003366;border-bottom:1px solid #003366;padding-bottom:4px}
table{font-size:12px;border-collapse:collapse;width:100%;margin-top:8px}td,th{border:1px solid #A0A0A0;padding:3px 7px;text-align:left}
th{background:#E4E0D2}code{background:#EEE;padding:1px 3px}
.pie{color:#666;font-size:10px;margin-top:12px}
.form2009{background:#EDEAE0;border:1px solid #A0A0A0;padding:10px;margin-top:10px}
.form2009 input{font-size:12px}
.error{color:#8B0000;font-weight:bold}
.pagada{color:#8B0000}.pendiente{color:#1E5B1E}
.nav2009{margin:8px 0}a{color:#003366}</style>"""

    def _portada(self, error: bool = False) -> None:
        assert ESTADO is not None
        aviso = '<p class="error">Credenciales no reconocidas. Consulte MANUAL_ERP_2009.md, seccion 2.</p>' if error else ""
        cuerpo = f"""<html>
<head><title>ERP Miralmar - Bridge AS/400</title><link rel="icon" href="data:,">{self.ESTILO_2009}</head>
<body><div class="caja">
<h1>ERP Miralmar &middot; bridge AS/400 v2.3.1</h1>
<p><b>El bridge esta funcionando.</b> Asientos cargados: <b>{len(ESTADO.asientos)}</b>.</p>
<div class="form2009">
<b>Consulta para personal de administracion</b> (usuario y clave: en el manual)
<form method="post" action="/erp/login">
<input type="hidden" name="origen" value="web">
Usuario <input name="usuario" value="alberto" size="10">
Clave <input type="password" name="clave" size="14">
<input type="submit" value="Entrar">
</form>
{aviso}</div>
<p style="margin-top:12px">Para sistemas, los recursos de siempre:</p>
<table>
<tr><th>Recurso</th><th>Uso</th></tr>
<tr><td><code>POST /erp/login</code></td><td>Identificacion (devuelve token de sesion)</td></tr>
<tr><td><code>GET /erp/asientos?pagina=N</code></td><td>Asientos contables, {PAGINA_TAMANO} por pagina, con token</td></tr>
<tr><td><code>GET /erp/asientos/AS-00412</code></td><td>Un asiento concreto, con token</td></tr>
<tr><td><code>GET /erp/estado</code></td><td>Salud del bridge (sin identificacion)</td></tr>
</table>
<p>Manual completo: <code>MANUAL_ERP_2009.md</code> (en la Caja). Si recibe <code>ORA-00600</code>, reintente la consulta. No llame a Mantenimiento.</p>
<p class="pie">Instalado en 2009 por J.M. &middot; No tocar &middot; Optimizado para Internet Explorer 7</p>
</div></body></html>"""
        self._responder(200, cuerpo, tipo="text/html")

    def _consulta_web(self, consulta: "dict[str, list[str]]") -> None:
        """Vista HTML para humanos: misma sesion, mismos datos y mismas averias que la API."""
        assert ESTADO is not None
        token = self._token(consulta) or ""
        with ESTADO.lock:
            autorizado = ESTADO.validar_sesion(token)
        if not autorizado:
            cuerpo = (f'<html><head><title>ERP Miralmar</title>{self.ESTILO_2009}</head><body><div class="caja">'
                      '<h1>Sesion no valida o caducada</h1><p>Las sesiones duran 15 minutos o 300 consultas. '
                      '<a href="/">Volver a identificarse</a>.</p></div></body></html>')
            self._responder(401, cuerpo, tipo="text/html")
            return
        with ESTADO.lock:
            falla = ESTADO.toca_fallo()
        if falla:
            cuerpo = (f'<html><head><title>ERP Miralmar</title>{self.ESTILO_2009}</head><body><div class="caja">'
                      '<h1 class="error">ORA-00600: error interno del nucleo</h1>'
                      '<p>Es normal. Pulse <b>Actualizar</b> (F5) y la consulta saldra. Si persiste, no llame a Mantenimiento.</p>'
                      '</div></body></html>')
            self._responder(500, cuerpo, tipo="text/html")
            return
        buscado = (consulta.get("asiento") or [""])[0].strip()
        with ESTADO.lock:
            filas = list(ESTADO.asientos)
        aviso = ""
        if buscado:
            encontrado = ESTADO.por_id.get(buscado)
            if encontrado:
                filas, total, paginas, pagina = [encontrado], 1, 1, 1
            else:
                aviso = f'<p class="error">El asiento {_xml_escape(buscado)} no consta en el sistema.</p>'
                filas, total, paginas, pagina = [], 0, 1, 1
        else:
            total = len(filas)
            paginas = max(1, (total + PAGINA_TAMANO - 1) // PAGINA_TAMANO)
            try:
                pagina = min(max(1, int((consulta.get("pagina") or ["1"])[0])), paginas)
            except ValueError:
                pagina = 1
            filas = filas[(pagina - 1) * PAGINA_TAMANO : pagina * PAGINA_TAMANO]
        celdas = "".join(
            f'<tr><td>{_xml_escape(f["asiento_id"])}</td><td>{_fecha_legacy(f["fecha_registro"])}</td>'
            f'<td>{_xml_escape(f["proveedor_id"])}</td><td>{_xml_escape(f["nif"])}</td>'
            f'<td>{_xml_escape(f["pedido"])}</td><td align="right">{_importe_legacy(f["importe_esperado"])}</td>'
            f'<td class="{f["estado"].lower()}">{_xml_escape(f["estado"])}</td></tr>'
            for f in filas
        )
        atras = f'<a href="/erp/consulta?token={token}&amp;pagina={pagina - 1}">&laquo; Anterior</a>' if pagina > 1 else "&laquo; Anterior"
        alante = f'<a href="/erp/consulta?token={token}&amp;pagina={pagina + 1}">Siguiente &raquo;</a>' if pagina < paginas else "Siguiente &raquo;"
        cuerpo = f"""<html>
<head><title>ERP Miralmar - Consulta de asientos</title><link rel="icon" href="data:,">{self.ESTILO_2009}</head>
<body><div class="caja">
<h1>Consulta de asientos contables</h1>
<form method="get" action="/erp/consulta" style="margin-top:6px">
<input type="hidden" name="token" value="{token}">
Buscar asiento <input name="asiento" value="{_xml_escape(buscado)}" size="12"> <input type="submit" value="Buscar">
&nbsp;&nbsp;<a href="/erp/consulta?token={token}">Ver todos</a>
</form>
{aviso}
<div class="nav2009">{atras} &nbsp; Pagina {pagina} de {paginas} &nbsp; {alante} &nbsp;&nbsp; ({total} asientos)</div>
<table>
<tr><th>Asiento</th><th>Fecha</th><th>Prov.</th><th>NIF</th><th>Pedido</th><th>Importe</th><th>Estado</th></tr>
{celdas}
</table>
<div class="nav2009">{atras} &nbsp; Pagina {pagina} de {paginas} &nbsp; {alante}</div>
<p class="pie">Sesion de consulta activa. Si ve ORA-00600, actualice la pagina. &middot; ERP Miralmar 2009</p>
</div></body></html>"""
        self._responder(200, cuerpo, tipo="text/html")

    def _listar_asientos(self, consulta: "dict[str, list[str]]") -> None:
        assert ESTADO is not None
        crudo = (consulta.get("pagina") or ["1"])[0]
        try:
            pagina = int(crudo)
        except ValueError:
            self._error_xml(400, "ERP-400", f"Parametro pagina invalido: {crudo}. Las paginas empiezan en 1.")
            return
        with ESTADO.lock:
            filas = list(ESTADO.asientos)
        total = len(filas)
        paginas = max(1, (total + PAGINA_TAMANO - 1) // PAGINA_TAMANO)
        if pagina < 1 or pagina > paginas:
            self._error_xml(400, "ERP-400", f"Pagina fuera de rango: {pagina}. Rango valido: 1 a {paginas}.")
            return
        trozo = filas[(pagina - 1) * PAGINA_TAMANO : pagina * PAGINA_TAMANO]
        cuerpo = io.StringIO()
        cuerpo.write('<?xml version="1.0" encoding="ISO-8859-1"?>\n<respuesta>\n')
        cuerpo.write(
            "  <meta>\n"
            f"    <total>{total}</total>\n"
            f"    <paginas>{paginas}</paginas>\n"
            f"    <pagina>{pagina}</pagina>\n"
            f"    <por_pagina>{PAGINA_TAMANO}</por_pagina>\n"
            f"    <generado>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</generado>\n"
            "  </meta>\n  <asientos>\n"
        )
        for fila in trozo:
            cuerpo.write(_xml_asiento(fila))
        cuerpo.write("  </asientos>\n</respuesta>\n")
        self._responder(200, cuerpo.getvalue())
        self.log_message("GET %s -> 200 (%d asientos, pagina %d/%d)", self.path, len(trozo), pagina, paginas)

    def _detalle_asiento(self, asiento_id: str) -> None:
        assert ESTADO is not None
        with ESTADO.lock:
            fila = ESTADO.por_id.get(asiento_id)
        if fila is None:
            self._error_xml(404, "ERP-404", f"El asiento {asiento_id} no consta en el sistema.")
            return
        cuerpo = (
            '<?xml version="1.0" encoding="ISO-8859-1"?>\n<respuesta>\n  <asientos>\n'
            + _xml_asiento(fila)
            + "  </asientos>\n</respuesta>\n"
        )
        self._responder(200, cuerpo)


def main() -> int:
    parser = argparse.ArgumentParser(description=VERSION)
    parser.add_argument("--puerto", type=int, default=8009, help="puerto local (por defecto 8009)")
    parser.add_argument("--lote2", help="CSV incremental de Alberto (sabado): se fusiona con los asientos")
    parser.add_argument("--rapido", action="store_true", help="sin latencia artificial (para tests)")
    args = parser.parse_args()

    global ESTADO
    asientos = _cargar_asientos_embebidos()
    ESTADO = EstadoERP(asientos, latencia=0.0 if args.rapido else 0.12)
    if args.lote2:
        nuevos, actualizados = ESTADO.cargar_lote2(_cargar_asientos_csv(args.lote2))
        print(f"[ERP 2009] actualizacion cargada: {nuevos} asientos nuevos, {actualizados} actualizados")

    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), ManejadorERP)
    except OSError as exc:
        print(f"ERROR: no puedo escuchar en el puerto {args.puerto} ({exc}). Prueba --puerto {args.puerto + 1}.", file=sys.stderr)
        return 1
    servidor.daemon_threads = True
    print(f"[ERP 2009] {VERSION}")
    print(f"[ERP 2009] escuchando en http://127.0.0.1:{args.puerto}  ·  asientos: {len(ESTADO.asientos)}")
    print("[ERP 2009] login: POST /erp/login (ver MANUAL_ERP_2009.md) · Ctrl+C para apagar (no lo sabra nadie)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n[ERP 2009] apagado ordenado. Hasta 2027.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
