"""Small standalone synthetic HTTP ERP for trying the app without downloading data."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/xml; charset=iso-8859-1")
        self.end_headers()
        self.wfile.write(body.encode("iso-8859-1"))

    def do_POST(self):
        if self.path != "/erp/login":
            return self.reply(404, "<error/>")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        fields = parse_qs(body)
        if fields.get("usuario") != ["alberto"] or fields.get("clave") != [
            "FACTURAS2009"
        ]:
            return self.reply(401, "<error/>")
        self.reply(200, "<erp><token>synthetic-demo-session</token></erp>")

    def do_GET(self):
        if self.headers.get("X-ERP-Token") != "synthetic-demo-session":
            return self.reply(401, "<error/>")
        if self.path != "/erp/asientos?pagina=1":
            return self.reply(404, "<error/>")
        records = "".join(
            f'<asiento><id>{i}</id><fecha>2026-02-01</fecha><proveedor>P001</proveedor><nif>B12345678</nif><pedido>PO-2026-{i:04}</pedido><importe>121.00</importe><estado>{"PAGADA" if i==3 else "PENDIENTE"}</estado></asiento>'
            for i in range(1, 4)
        )
        self.reply(
            200,
            f"<erp><meta><total>3</total><paginas>1</paginas></meta><asientos>{records}</asientos></erp>",
        )


if __name__ == "__main__":
    print(
        "ERP SINTÉTICO en http://127.0.0.1:8019. No sustituye las pruebas con el ERP oficial.",
        flush=True,
    )
    HTTPServer(("127.0.0.1", 8019), Handler).serve_forever()
