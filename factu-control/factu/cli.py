from __future__ import annotations

import argparse
import json
import os
import sys

from .service import Service


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="factu", description="FactU Control - facturas con evidencia"
    )
    parser.add_argument("--data", default=os.getenv("FACTU_DATA", "data"))
    sub = parser.add_subparsers(dest="command", required=True)
    lote1 = sub.add_parser("lote1", help="Importa/reanuda las 500 facturas oficiales, consulta el ERP y procesa todo")
    lote1.add_argument("--materials", required=True, help="Carpeta oficial con facturas/ y FINAL_v7_DEFINITIVO_ahorasi.xlsx")
    lote1.add_argument("--as-of", required=True, help="Fecha de referencia explícita YYYY-MM-DD")
    lote1.add_argument("--url", default=os.getenv("ERP_URL", "http://127.0.0.1:8009"))
    lote1.add_argument("--user", default=os.getenv("ERP_USER", "alberto"))
    lote1.add_argument("--serve", action="store_true", help="Abre el servidor web con el mismo estado al terminar")
    lote1.add_argument("--port", type=int, default=8089)
    ingest = sub.add_parser(
        "ingest", help="Importa originales y registra un manifiesto"
    )
    ingest.add_argument("--pdfs", required=True)
    ingest.add_argument("--excel", required=True)
    ingest.add_argument("--name", required=True)
    ingest.add_argument("--as-of", required=True)
    ingest.add_argument("--policy")
    ingest.add_argument("--actor", default="equipo")
    sync = sub.add_parser("sync-erp", help="Obtiene un snapshot completo por HTTP")
    sync.add_argument("batch")
    sync.add_argument("--url", default=os.getenv("ERP_URL", "http://127.0.0.1:8009"))
    sync.add_argument("--user", default=os.getenv("ERP_USER", "alberto"))
    for name in (
        "process",
        "retry",
        "reextract",
        "evaluate",
        "metrics",
        "export",
        "policy",
    ):
        p = sub.add_parser(name)
        p.add_argument("batch")
        if name == "process":
            p.add_argument("--no-ocr", action="store_true")
            p.add_argument("--limit", type=int)
            p.add_argument(
                "--fault-after",
                type=int,
                help="Simula interrupción antes del commit; lease recuperable",
            )
        if name == "export":
            p.add_argument("--output", required=True)
        if name == "policy":
            p.add_argument("--file", required=True)
            p.add_argument("--actor", required=True)
    sub.add_parser("batches")
    sub.add_parser("verify-audit")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", default=8080, type=int)
    args = parser.parse_args(argv)
    service = Service(args.data)
    try:
        if args.command == "lote1":
            from .lote1 import run_lote1
            result = run_lote1(service, args.materials, args.as_of, args.url, args.user,
                               os.getenv("ERP_PASSWORD", "FACTURAS2009"))
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            print(f"Bandeja: http://127.0.0.1:{args.port}/?batch={result['batch_id']}", flush=True)
            if args.serve:
                import uvicorn
                from .web import create_app
                os.environ["ERP_URL"] = args.url
                uvicorn.run(create_app(args.data), host="127.0.0.1", port=args.port)
            return
        elif args.command == "ingest":
            result = service.ingest(
                args.pdfs, args.excel, args.name, args.as_of, args.policy, args.actor
            )
        elif args.command == "sync-erp":
            result = service.sync_erp(
                args.batch,
                args.url,
                args.user,
                os.getenv("ERP_PASSWORD", "FACTURAS2009"),
            )
        elif args.command == "process":
            result = service.process(
                args.batch, not args.no_ocr, args.limit, args.fault_after
            )
        elif args.command == "retry":
            result = service.retry(args.batch)
        elif args.command == "reextract":
            result = service.reextract(args.batch)
        elif args.command == "evaluate":
            result = service.reevaluate_all()
        elif args.command == "export":
            result = service.export(args.batch, args.output)
        elif args.command == "policy":
            result = service.change_policy(args.batch, args.file, args.actor)
        elif args.command == "metrics":
            result = service.dashboard(args.batch)["metrics"]
        elif args.command == "batches":
            result = service.store.all("SELECT * FROM batches ORDER BY created")
        elif args.command == "verify-audit":
            result = service.store.verify_audit()
        elif args.command == "serve":
            import uvicorn
            from .web import create_app

            uvicorn.run(create_app(args.data), host="127.0.0.1", port=args.port)
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
