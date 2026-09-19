#!/usr/bin/env python3
"""Evaluación trazable del extractor específico del lote 2.

No es un generador de etiquetas ni un verificador de decisiones de pago. Mide
el perfil completo (texto nativo + parser + testigo RapidOCR cuando aplica)
contra transcripciones manuales internas. ``test`` es un *holdout* agrupado
retrospectivo de desarrollo, no una validación privada ni ciega del jurado.
Si no hay etiquetas, falla: medir solamente cobertura del OCR no es medir
exactitud.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from factu import lote2_ocr
from factu.extract import FIELDS, extract_pdf
from factu.utils import clean, identifier, invoice_date, money


PROFILE = "lote2_ocr_v1"
EVALUATED_FIELDS = (*FIELDS, "currency")
# ``invoice_number`` es informativo en la política v3. Los demás campos sí
# bloquean una decisión automática y, por tanto, forman el umbral prudente de
# autoaceptación documental.
AUTOACCEPT_FIELDS = tuple(field for field in EVALUATED_FIELDS if field != "invoice_number")
SPLIT_NAMES = ("train", "validation", "test")
BLOCKING_WARNINGS = {"OCR_EMPTY", "OCR_UNAVAILABLE", "OCR_DISABLED"}
ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_FILES = (
    "scripts/evaluate_lote2_ocr.py",
    "factu/extract.py",
    "factu/lote2_ocr.py",
    "factu/policy.py",
    "pyproject.toml",
    "requirements.lock",
)


class EvaluationError(ValueError):
    """El protocolo no permite producir una métrica defendible."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    """Hash estable para un manifiesto JSON, sin depender de su formato."""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _code_manifest() -> dict[str, str]:
    """Huella del código que define la lectura y la decisión evaluada."""

    return {
        relative: _sha256(ROOT / relative)
        for relative in PROVENANCE_FILES
        if (ROOT / relative).is_file()
    }


def _normalise_currency(value: Any) -> str:
    """Normaliza únicamente nombres o símbolos inequívocos a ISO 4217.

    Un ``$`` aislado es deliberadamente inválido: no se puede convertir en USD
    sin mirar la factura. Las etiquetas deben anotar el código ISO que verificó
    la persona, no una suposición geográfica.
    """

    raw = clean(value).upper()
    aliases = {
        "EUR": "EUR",
        "€": "EUR",
        "EURO": "EUR",
        "EUROS": "EUR",
        "USD": "USD",
        "US$": "USD",
        "DOLLAR": "USD",
        "DOLLARS": "USD",
        "DÓLAR": "USD",
        "DÓLARES": "USD",
        "JPY": "JPY",
        "¥": "JPY",
        "YEN": "JPY",
        "YENES": "JPY",
        "GBP": "GBP",
        "£": "GBP",
        "CHF": "CHF",
        "BRL": "BRL",
        "R$": "BRL",
        "MXN": "MXN",
        "MX$": "MXN",
    }
    if raw == "$":
        raise EvaluationError("La moneda '$' es ambigua; etiqueta EUR, USD, JPY, etc.")
    if raw not in aliases:
        raise EvaluationError(f"Moneda de etiqueta no reconocida: {value!r}")
    return aliases[raw]


def normalise_value(field: str, value: Any) -> str | None:
    """Clave de comparación exacta después de la normalización de dominio."""

    if value is None:
        return None
    if field in {"invoice_number", "supplier_nif", "iban", "order"}:
        return identifier(value)
    if field == "date":
        return invoice_date(str(value))
    if field in {"base", "tax_rate", "tax_amount", "total"}:
        # La igualdad decimal acepta 121,0 == 121.00 sin ocultar diferencias
        # reales como 121.00 != 121.01.
        return format(money(value).normalize(), "f")
    if field == "currency":
        return _normalise_currency(value)
    raise EvaluationError(f"Campo no evaluable: {field}")


def _load_json(path: Path, kind: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvaluationError(f"No existe el fichero de {kind}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"JSON inválido de {kind}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise EvaluationError(f"El fichero de {kind} debe contener un objeto JSON")
    return loaded


def _labels_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    documents = payload.get("documents")
    if not isinstance(documents, dict) or not documents:
        raise EvaluationError(
            "No hay etiquetas manuales. No se puede proclamar exactitud sin verdad de referencia."
        )
    result: dict[str, dict[str, Any]] = {}
    labelled_values = 0
    for filename, document in documents.items():
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise EvaluationError("Cada etiqueta debe usar solo el nombre del PDF, sin rutas")
        if not isinstance(document, dict):
            raise EvaluationError(f"Etiqueta inválida para {filename}")
        fields = document.get("fields")
        if not isinstance(fields, dict):
            raise EvaluationError(f"Falta el objeto fields en {filename}")
        normalized: dict[str, str | None] = {}
        for field, entry in fields.items():
            if field not in EVALUATED_FIELDS:
                raise EvaluationError(f"Campo de etiqueta no soportado en {filename}: {field}")
            if isinstance(entry, dict):
                if "value" not in entry:
                    raise EvaluationError(f"Falta fields.{field}.value en {filename}")
                entry = entry["value"]
            try:
                normalized[field] = normalise_value(field, entry)
            except (ValueError, ArithmeticError, EvaluationError) as exc:
                raise EvaluationError(
                    f"Etiqueta inválida para {filename}.{field}: {exc}"
                ) from exc
            labelled_values += 1
        result[filename] = {
            "fields": normalized,
            "template_id": document.get("template_id"),
            "supplier_id": document.get("supplier_id"),
        }
    if not labelled_values:
        raise EvaluationError(
            "Las etiquetas no contienen ningún campo verificable; no se puede medir accuracy."
        )
    return result


def _split_assignments(payload: dict[str, Any], labels: set[str]) -> dict[str, str]:
    splits = payload.get("splits")
    if not isinstance(splits, dict):
        raise EvaluationError("El fichero de splits debe contener un objeto splits")
    if set(splits) != set(SPLIT_NAMES):
        raise EvaluationError("Los splits deben ser exactamente train, validation y test")
    assignment: dict[str, str] = {}
    for split in SPLIT_NAMES:
        names = splits[split]
        if not isinstance(names, list) or not names:
            raise EvaluationError(f"El split {split} debe contener al menos un PDF etiquetado")
        for filename in names:
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise EvaluationError(f"Nombre de PDF inválido en el split {split}: {filename!r}")
            if filename in assignment:
                raise EvaluationError(
                    f"Fuga entre splits: {filename} está en {assignment[filename]} y {split}"
                )
            assignment[filename] = split
    missing = labels - set(assignment)
    extra = set(assignment) - labels
    if missing:
        raise EvaluationError("Faltan etiquetas en el split para: " + ", ".join(sorted(missing)))
    if extra:
        raise EvaluationError("El split contiene PDFs sin etiqueta: " + ", ".join(sorted(extra)))
    return assignment


def _check_group_isolation(labels: dict[str, dict[str, Any]], assignment: dict[str, str]) -> None:
    """Evita que un grupo declarado aparezca en más de un split.

    El chequeo valida los identificadores que aporta el dataset; no demuestra
    por sí solo que ``template_id`` sea un layout visual independiente.
    """

    for grouping in ("template_id", "supplier_id"):
        group_splits: dict[str, set[str]] = defaultdict(set)
        missing = []
        for filename, record in labels.items():
            group = record.get(grouping)
            if not isinstance(group, str) or not group.strip():
                missing.append(filename)
                continue
            group_splits[group.strip()].add(assignment[filename])
        if missing:
            raise EvaluationError(
                f"--strict-groups requiere {grouping} en todas las etiquetas; faltan: "
                + ", ".join(sorted(missing))
            )
        leaked = [
            f"{group} ({', '.join(sorted(splits))})"
            for group, splits in group_splits.items()
            if len(splits) > 1
        ]
        if leaked:
            raise EvaluationError(
                f"Fuga por {grouping}: " + "; ".join(sorted(leaked))
            )


def _empty_counters() -> dict[str, dict[str, int]]:
    return {
        field: {
            "labelled": 0,
            "exact": 0,
            "autoaccepted": 0,
            "autoaccepted_exact": 0,
        }
        for field in EVALUATED_FIELDS
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _field_metrics(counter: dict[str, int]) -> dict[str, int | float | None]:
    labelled = counter["labelled"]
    accepted = counter["autoaccepted"]
    accepted_exact = counter["autoaccepted_exact"]
    return {
        "labelled": labelled,
        "exact": counter["exact"],
        "exact_match_accuracy": _ratio(counter["exact"], labelled),
        "autoaccepted": accepted,
        # Precision: si el extractor dice que el campo está listo para usar,
        # cuántas veces coincide con la etiqueta independiente.
        "autoaccept_precision": _ratio(accepted_exact, accepted),
        # Cobertura: cuántas etiquetas reciben una lectura autoaceptable.
        "autoaccept_coverage": _ratio(accepted, labelled),
        # Cobertura segura: cuántas se autoaceptaron *y* eran correctas.
        "autoaccept_safe_coverage": _ratio(accepted_exact, labelled),
    }


def _summary(
    counters: dict[str, dict[str, int]], document_counts: dict[str, int], methods: Counter[str]
) -> dict[str, Any]:
    fields = {field: _field_metrics(counter) for field, counter in counters.items() if counter["labelled"]}
    accuracies = [m["exact_match_accuracy"] for m in fields.values() if m["exact_match_accuracy"] is not None]
    precisions = [m["autoaccept_precision"] for m in fields.values() if m["autoaccept_precision"] is not None]
    return {
        "documents_labelled": document_counts["labelled"],
        "documents_with_full_autoaccept_labels": document_counts["eligible"],
        "documents_autoaccepted": document_counts["autoaccepted"],
        "documents_autoaccepted_exact": document_counts["autoaccepted_exact"],
        "document_autoaccept_precision": _ratio(
            document_counts["autoaccepted_exact"], document_counts["autoaccepted"]
        ),
        "document_autoaccept_coverage": _ratio(
            document_counts["autoaccepted"], document_counts["eligible"]
        ),
        "document_autoaccept_safe_coverage": _ratio(
            document_counts["autoaccepted_exact"], document_counts["eligible"]
        ),
        "document_autoaccept_lot_coverage": _ratio(
            document_counts["autoaccepted_exact"], document_counts["labelled"]
        ),
        "macro_exact_match_accuracy": round(mean(accuracies), 6) if accuracies else None,
        "macro_autoaccept_precision": round(mean(precisions), 6) if precisions else None,
        "field_metrics": fields,
        "pages_by_method": dict(sorted(methods.items())),
    }


def _autoaccepted_field(field: dict[str, Any]) -> bool:
    """Un campo solo está listo si el extractor lo marca OK y tiene un valor."""

    return field.get("status") == "OK" and field.get("value") is not None


def _document_autoaccepted(extraction: dict[str, Any], labels: dict[str, str | None]) -> bool | None:
    # Si la persona no etiquetó todos los campos de riesgo, no se calcula una
    # métrica documental: se evita llamar "precisión de autoaceptación" a una
    # medición parcial.
    if any(field not in labels for field in AUTOACCEPT_FIELDS):
        return None
    if extraction.get("untrusted_instructions"):
        return False
    if any(warning.get("code") in BLOCKING_WARNINGS for warning in extraction.get("warnings", [])):
        return False
    fields = extraction.get("fields", {})
    return all(_autoaccepted_field(fields.get(field, {})) for field in AUTOACCEPT_FIELDS)


def _document_exact(extraction: dict[str, Any], labels: dict[str, str | None]) -> bool:
    for field in AUTOACCEPT_FIELDS:
        observed = extraction.get("fields", {}).get(field, {})
        if not _autoaccepted_field(observed):
            return False
        try:
            value = normalise_value(field, observed.get("value"))
        except (ValueError, ArithmeticError, EvaluationError):
            return False
        if value != labels[field]:
            return False
    return True


def _extract_with_lote2_profile(
    path: Path, *, ocr: bool, profile: str = PROFILE
) -> dict[str, Any]:
    """Llamada centralizada para que nunca se evalúe accidentalmente lote 1."""

    try:
        return extract_pdf(path, ocr=ocr, profile=profile)
    except TypeError as exc:
        # Mensaje accionable mientras una rama antigua aún no ha incorporado el
        # perfil, en lugar de medir sin querer la ruta por defecto.
        if "profile" in str(exc):
            raise EvaluationError(
                f"La versión instalada no implementa el perfil {profile}; no se evaluó la ruta equivocada."
            ) from exc
        raise


def evaluate(
    pdfs: Path | str,
    labels_payload: dict[str, Any],
    splits_payload: dict[str, Any],
    *,
    extractor: Callable[..., dict[str, Any]] | None = None,
    ocr: bool = True,
    strict_groups: bool = False,
    profile: str = PROFILE,
) -> dict[str, Any]:
    """Evalúa PDFs etiquetados sin usar decisiones de negocio como etiquetas."""

    pdfs_path = Path(pdfs)
    if not pdfs_path.is_dir():
        raise EvaluationError(f"No existe el directorio de PDFs: {pdfs_path}")
    if not isinstance(profile, str) or not profile.strip():
        raise EvaluationError("El perfil de extracción debe ser un nombre no vacío")
    labels = _labels_from_payload(labels_payload)
    assignment = _split_assignments(splits_payload, set(labels))
    if strict_groups:
        _check_group_isolation(labels, assignment)
    extraction_fn = extractor or _extract_with_lote2_profile
    counters_by_split = {split: _empty_counters() for split in SPLIT_NAMES}
    documents_by_split = {
        split: {"labelled": 0, "eligible": 0, "autoaccepted": 0, "autoaccepted_exact": 0}
        for split in SPLIT_NAMES
    }
    methods_by_split = {split: Counter() for split in SPLIT_NAMES}
    extraction_versions: set[str] = set()
    engines_observed: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    for filename in sorted(labels):
        path = pdfs_path / filename
        if not path.is_file():
            raise EvaluationError(f"La etiqueta apunta a un PDF inexistente: {filename}")
        split = assignment[filename]
        try:
            extraction = extraction_fn(path, ocr=ocr, profile=profile)
        except TypeError as exc:
            # Un extractor inyectado por tests debe respetar la misma firma.
            raise EvaluationError(f"Extractor incompatible para {filename}: {exc}") from exc
        if not isinstance(extraction, dict) or not isinstance(extraction.get("fields"), dict):
            raise EvaluationError(f"El extractor no devolvió fields para {filename}")
        # La evaluación nunca debe mezclar el perfil normal de lote 1 con el
        # perfil experimental de lote 2. ``profile`` es el contrato fuerte;
        # ``version`` aporta además una huella humana legible para el informe.
        actual_profile = extraction.get("profile")
        version = extraction.get("version")
        if actual_profile != profile or not isinstance(version, str) or not version.strip():
            raise EvaluationError(
                f"El extractor devolvió profile/version incompatibles para {filename}: "
                f"profile={actual_profile!r}, version={version!r}; se esperaba profile={profile!r}."
            )
        extraction_versions.add(version)
        engines = extraction.get("engines")
        if isinstance(engines, dict):
            engines_observed.setdefault(_canonical_sha256(engines), engines)
        documents_by_split[split]["labelled"] += 1
        for page in extraction.get("pages", []):
            method = page.get("method")
            if isinstance(method, str):
                methods_by_split[split][method] += 1
            # Lote 2 conserva PyMuPDF como lectura principal y guarda
            # RapidOCR como ``witness_method``. Contar ambos evita presentar
            # falsamente una evaluación OCR como si fuera solo texto nativo.
            witness_method = page.get("witness_method")
            if isinstance(witness_method, str):
                methods_by_split[split][witness_method] += 1
        label_fields = labels[filename]["fields"]
        for field, expected in label_fields.items():
            counter = counters_by_split[split][field]
            counter["labelled"] += 1
            observed = extraction["fields"].get(field, {})
            accepted = _autoaccepted_field(observed)
            actual = None
            normalization_error = None
            if observed.get("value") is not None:
                try:
                    actual = normalise_value(field, observed.get("value"))
                except (ValueError, ArithmeticError, EvaluationError) as exc:
                    normalization_error = str(exc)
                    accepted = False
            # Una etiqueta ``null`` quiere decir "la persona confirmó que el
            # campo no está impreso". Que el extractor lo deje MISSING es una
            # detección correcta de ausencia, pero nunca una autoaceptación.
            exact = (
                observed.get("status") == "MISSING" and observed.get("value") is None
                if expected is None
                else accepted and actual == expected
            )
            counter["exact"] += int(exact)
            counter["autoaccepted"] += int(accepted)
            # Una ausencia detectada correctamente (expected=null) suma a
            # exact match, pero no puede contar como una autoaceptación.
            counter["autoaccepted_exact"] += int(accepted and exact)
            if not exact:
                errors.append(
                    {
                        "file_id": filename,
                        "split": split,
                        "field": field,
                        "expected": expected,
                        "observed": actual,
                        "status": observed.get("status"),
                        "normalization_error": normalization_error,
                    }
                )
        document_accept = _document_autoaccepted(extraction, label_fields)
        if document_accept is not None:
            documents_by_split[split]["eligible"] += 1
            documents_by_split[split]["autoaccepted"] += int(document_accept)
            document_exact = _document_exact(extraction, label_fields)
            documents_by_split[split]["autoaccepted_exact"] += int(
                document_accept and document_exact
            )

    overall_counters = _empty_counters()
    overall_documents = {"labelled": 0, "eligible": 0, "autoaccepted": 0, "autoaccepted_exact": 0}
    overall_methods: Counter[str] = Counter()
    for split in SPLIT_NAMES:
        for field in EVALUATED_FIELDS:
            for key, value in counters_by_split[split][field].items():
                overall_counters[field][key] += value
        for key, value in documents_by_split[split].items():
            overall_documents[key] += value
        overall_methods.update(methods_by_split[split])
    available_pdfs = {path.name for path in pdfs_path.glob("*.pdf")}
    pdf_manifest = {filename: _sha256(pdfs_path / filename) for filename in sorted(labels)}
    profile_identity = (
        lote2_ocr.cache_identity()
        if profile == PROFILE
        else {"profile": profile, "identity": "extractor supplied by caller"}
    )
    report = {
        "schema_version": "factu-lote2-ocr-evaluation-v1",
        "profile": profile,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "exact_match": "Valores normalizados por tipo; no compara decisiones de pago.",
            "automatic_field_acceptance": "status=OK y valor no vacío.",
            "automatic_document_acceptance": (
                "Todos los campos de riesgo OK, sin warning de OCR ni instrucciones no fiables."
            ),
            "evaluation_split_role": (
                "train/validation/test es una partición retrospectiva interna; "
                "test es holdout agrupado de desarrollo, no prueba ciega ni privada."
            ),
            "strict_groups": strict_groups,
        },
        "overall": _summary(overall_counters, overall_documents, overall_methods),
        "splits": {
            split: _summary(
                counters_by_split[split], documents_by_split[split], methods_by_split[split]
            )
            for split in SPLIT_NAMES
        },
        "errors": errors,
        "unlabelled_pdf_files": sorted(available_pdfs - set(labels)),
        "limitations": [
            "Las etiquetas son transcripciones manuales internas revisadas; no sustituyen una doble anotación independiente.",
            "Una coincidencia de campos no equivale a autorizar un pago; las reglas y el ERP siguen decidiendo.",
            "No se publica una accuracy si faltan etiquetas o si un PDF aparece en más de un split.",
            "La agrupación usa los IDs declarados por el dataset; un template_id derivado del proveedor no prueba independencia de layout visual.",
        ],
        "provenance": {
            "profile_identity": profile_identity,
            "extraction_versions": sorted(extraction_versions),
            "engine_sets_observed": list(engines_observed.values()),
            "pdf_sha256": pdf_manifest,
            "pdf_manifest_sha256": _canonical_sha256(pdf_manifest),
            "code_sha256": _code_manifest(),
            "runtime": {
                "python": sys.version,
                "implementation": platform.python_implementation(),
                "platform": platform.platform(),
            },
        },
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdfs", required=True, type=Path, help="Directorio con los PDFs del lote 2")
    parser.add_argument("--labels", required=True, type=Path, help="JSON de transcripciones manuales")
    parser.add_argument("--splits", required=True, type=Path, help="JSON train/validation/test")
    parser.add_argument("--report", required=True, type=Path, help="JSON de métricas reproducible")
    parser.add_argument(
        "--profile",
        default=PROFILE,
        help=f"Perfil que se evalúa (por defecto: {PROFILE})",
    )
    parser.add_argument("--no-ocr", action="store_true", help="Solo para comparar una línea base sin OCR")
    parser.add_argument(
        "--strict-groups",
        action="store_true",
        help="Exige que los IDs de proveedor/plantilla declarados no crucen train/validation/test",
    )
    args = parser.parse_args(argv)
    try:
        labels_payload = _load_json(args.labels, "etiquetas")
        splits_payload = _load_json(args.splits, "splits")
        report = evaluate(
            args.pdfs,
            labels_payload,
            splits_payload,
            ocr=not args.no_ocr,
            strict_groups=args.strict_groups,
            profile=args.profile,
        )
    except EvaluationError as exc:
        parser.error(str(exc))
    report["inputs"] = {
        "labels": {"path": str(args.labels), "sha256": _sha256(args.labels)},
        "splits": {"path": str(args.splits), "sha256": _sha256(args.splits)},
        "pdf_directory": str(args.pdfs),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
