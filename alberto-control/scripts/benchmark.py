"""End-to-end measurement, including real ERP latency and retries; no hidden labels."""

import argparse
import json
import os
import platform
import resource
import time
from pathlib import Path
from alberto.service import Service


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pdfs", required=True)
    p.add_argument("--excel", required=True)
    p.add_argument(
        "--data",
        required=True,
        help="Use a new empty directory for a cold-cache benchmark",
    )
    p.add_argument("--erp", default="http://127.0.0.1:8009")
    p.add_argument("--as-of", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--label", default="ERP normal, OCR local")
    p.add_argument(
        "--erp-mode",
        choices=["normal", "fast", "unknown"],
        default="unknown",
        help="Modo declarado por quien arranca el ERP; no se autodetecta",
    )
    args = p.parse_args()
    if (Path(args.data) / "alberto.sqlite3").exists():
        p.error(
            "Use an empty data directory; this benchmark must not overwrite previous runs"
        )
    start = time.monotonic()
    service = Service(args.data)
    batch = service.ingest(args.pdfs, args.excel, "Benchmark", args.as_of)["batch_id"]
    ingest_seconds = time.monotonic() - start
    erp_start = time.monotonic()
    erp = service.sync_erp(
        batch,
        args.erp,
        os.getenv("ERP_USER", "alberto"),
        os.getenv("ERP_PASSWORD", "FACTURAS2009"),
    )
    erp_seconds = time.monotonic() - erp_start
    run = service.process(batch)
    elapsed = time.monotonic() - start
    metrics = service.dashboard(batch)["metrics"]
    pages = service.store.all("SELECT extraction FROM documents")
    extracted = [json.loads(row["extraction"]) for row in pages if row["extraction"]]
    methods = {}
    for x in extracted:
        for page in x["pages"]:
            methods[page["method"]] = methods.get(page["method"], 0) + 1
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() != "Darwin":
        rss *= 1024
    report = {
        "code_sha256": service.code_sha256,
        "label": args.label,
        "batch_id": batch,
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "python": platform.python_version(),
            "peak_rss_mib": round(rss / 1024**2, 2),
        },
        "measurement": {
            "cache": "cold",
            "workers": 1,
            "erp_mode_declared": args.erp_mode,
            "end_to_end_seconds": elapsed,
            "ingest_seconds": ingest_seconds,
            "erp_seconds": erp_seconds,
            "seconds_per_document": elapsed / metrics["documents"],
            "documents_per_minute": 60 * metrics["documents"] / elapsed,
            "pages_by_method": methods,
            "erp": erp,
            "run": run,
            "metrics": metrics,
            "audit": service.store.verify_audit(),
        },
        "limitations": [
            "Throughput measured on this batch and hardware, not a scale guarantee.",
            "No independent reference labels: classification accuracy is unknown.",
            "No paid inference calls; infrastructure and human costs are not valued.",
            "OCR score is not a calibrated probability of correctness.",
        ],
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
