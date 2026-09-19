"""Human decisions and versioned changes. No ERP writes, no silent source overrides."""
from __future__ import annotations

import copy
import json
import secrets
import time
from pathlib import Path

from .erp import ERPClient
from .master import read_master
from .policy import validate_policy
from .utils import canonical, clean, digest, identifier, now


class WorkspaceMixin:
    # Public mutation methods acquire Service.exclusive through a wrapper below.
    def human_preview(self, doc_id, result, actor, reason, evidence, acknowledged, seconds=0):
        doc = self.document(doc_id)
        if not doc["latest_decision"] or self.store.one("SELECT count(*) n FROM jobs WHERE state!='DONE'")["n"]:
            raise ValueError("Termina las comprobaciones técnicas antes de responder")
        if result not in ("PAGAR", "NO_PAGAR", "ESCALAR"):
            raise ValueError("Respuesta no admitida")
        if not clean(actor) or len(clean(reason)) < 20 or len(clean(evidence)) < 10:
            raise ValueError("Indica quién responde, el motivo (20 caracteres) y una referencia de evidencia (10 caracteres)")
        if not 0 <= float(seconds) <= 14400:
            raise ValueError("Tiempo de revisión fuera de rango")
        engine = self.evaluation(doc, with_human=False)
        if not engine:
            raise ValueError("Falta evidencia técnica para responder")
        blockers = [r for r in engine["rules"] if r["state"] != "PASS"]
        if result == "PAGAR":
            # A business answer may resolve source precedence / an extra business rule.
            # It cannot invent unreadable fields or bypass account, amount, duplicate or paid checks.
            protected = [r for r in blockers if r["state"] == "UNKNOWN" or
                         not (r["id"] in ("source_identity_conflict", "document_instructions") or r["id"].startswith("extra:"))]
            if engine["result"] == "NO_PAGAR" or protected:
                raise ValueError("No se puede proponer pagar: corrige primero las fuentes o lecturas. No se omiten controles de cuenta, identidad, importe, duplicados ni pagos previos.")
            if set(acknowledged) != {r["id"] for r in blockers}:
                raise ValueError("Confirma expresamente cada discrepancia de negocio revisada")
        answer = {"document_id": doc_id, "result": result, "actor": clean(actor),
                  "reason": clean(reason), "evidence": clean(evidence),
                  "acknowledged": sorted(set(acknowledged)), "seconds": float(seconds),
                  "anchor": engine["human_anchor"], "before": self.detail(doc_id)["decision"]["result"],
                  "engine_result": engine["result"], "blockers": [r["id"] for r in blockers]}
        answer["preview_token"] = digest({"answer": answer, "latest": doc["latest_decision"],
                                         "last_answer": self.store.one("SELECT max(id) n FROM human_decisions WHERE document_id=?", (doc_id,))["n"]})
        return answer

    def human_commit(self, doc_id, result, actor, reason, evidence, acknowledged, seconds, preview_token):
        preview = self.human_preview(doc_id, result, actor, reason, evidence, acknowledged, seconds)
        if preview_token != preview["preview_token"]:
            raise ValueError("La evidencia cambió. Previsualiza la respuesta de nuevo")
        doc = self.document(doc_id)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO human_decisions(document_id,anchor,result,actor,reason,evidence,acknowledged,seconds,created) VALUES(?,?,?,?,?,?,?,?,?)",
                       (doc_id, preview["anchor"], result, preview["actor"], preview["reason"], preview["evidence"], canonical(preview["acknowledged"]), seconds, now()))
            db.execute("UPDATE documents SET latest_decision=NULL WHERE id=?", (doc_id,))
            self.store.event("alberto_answered", preview, doc_id, doc["batch_id"], db)
            self.store.cost("human_review", seconds, doc_id, doc["batch_id"], {"declared_by": actor, "timing": "self_reported"}, db=db)
        self.evaluate_batch(doc["batch_id"], [doc_id])
        return preview

    def retract_human_answer(self, doc_id, actor, reason):
        """Retira la ultima respuesta humana sin borrarla: no se toca ni una
        fila existente de human_decisions, solo se sellan tres columnas
        nuevas (retracted_at/by/reason) que no forman parte de ningun
        anclaje ya sellado -- verify_audit() solo compara las columnas que
        existian cuando el evento "alberto_answered" se sello, asi que
        marcar la retractacion no rompe esa comprobacion.
        """
        doc = self.document(doc_id)
        if not clean(actor) or len(clean(reason)) < 10:
            raise ValueError("Indica quién retira la respuesta y por qué (10 caracteres)")
        answer = self.store.one(
            "SELECT * FROM human_decisions WHERE document_id=? AND retracted_at IS NULL ORDER BY id DESC LIMIT 1",
            (doc_id,),
        )
        if not answer:
            raise ValueError("No hay ninguna respuesta vigente que retirar")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT retracted_at FROM human_decisions WHERE id=?", (answer["id"],)
            ).fetchone()
            if current["retracted_at"] is not None:
                raise ValueError("Esa respuesta ya se retiró; recarga y compruébalo")
            db.execute(
                "UPDATE human_decisions SET retracted_at=?,retracted_by=?,retracted_reason=? WHERE id=?",
                (now(), clean(actor), clean(reason), answer["id"]),
            )
            db.execute("UPDATE documents SET latest_decision=NULL WHERE id=?", (doc_id,))
            self.store.event(
                "human_answer_retracted",
                {"original_actor": answer["actor"], "original_result": answer["result"],
                 "retracted_by": clean(actor), "reason": clean(reason)},
                doc_id, doc["batch_id"], db, records=[("human_decisions", answer["id"])],
            )
        self.evaluate_batch(doc["batch_id"], [doc_id])
        return {"retracted_id": answer["id"]}

    def _change_dependencies(self, doc, kind, source):
        fields = self.effective(doc)["fields"]
        def value(name):
            field = fields.get(name, {})
            return field.get("value") if field.get("status") == "OK" else None
        order, nif = value("order"), value("supplier_nif")
        if kind == "policy":
            return source  # New policy always gets a full rules replay; no OCR.
        if not order or kind == "master" and not nif:
            return source  # Unknown dependencies require conservative invalidation.
        if kind == "erp":
            return {"complete": source.get("complete"), "rows": sorted(
                [r for r in source["rows"] if identifier(r["pedido"]) == identifier(order)], key=canonical)}
        return {"suppliers": sorted([s for rows in source["suppliers"].values() for s in rows if s["nif"] == identifier(nif)], key=canonical),
                "orders": source["orders"].get(identifier(order), []), "rules": source["rules"]}

    def _change_guard(self, batch_id):
        return digest({"batch": self.batch(batch_id), "code": self.code_sha256,
                       "documents": self.store.all("SELECT id,sha256,extraction,latest_decision FROM documents ORDER BY id"),
                       "reviews": self.store.all("SELECT * FROM reviews ORDER BY id"),
                       "human": self.store.all("SELECT * FROM human_decisions ORDER BY id"),
                       "jobs": self.store.all("SELECT * FROM jobs ORDER BY id")})

    def preview_source(self, batch_id, kind, new_id, actor, reason, rules_ack=False):
        if kind not in ("master", "erp", "policy"):
            raise ValueError("Tipo de fuente desconocido")
        if not clean(actor) or len(clean(reason)) < 10:
            raise ValueError("Indica responsable y motivo del cambio")
        if self.store.one("SELECT count(*) n FROM jobs WHERE state!='DONE'")["n"]:
            raise ValueError("Termina los trabajos pendientes antes de cambiar fuentes")
        batch = self.batch(batch_id)
        key = {"master": "master_id", "erp": "snapshot_id", "policy": "policy_id"}[kind]
        if not batch["snapshot_id"]:
            raise ValueError("Primero sincroniza un ERP completo")
        old_id = batch[key]
        old, new = self.store.source(old_id), self.store.source(new_id)
        if kind == "erp" and not new.get("complete"):
            raise ValueError("El snapshot ERP debe ser completo")
        rules_changed = kind == "master" and old["rules"] != new["rules"]
        if rules_changed and not rules_ack:
            raise ValueError("La norma del Excel ha cambiado. Revisa primero la política implementada y confirma su correspondencia; no se traduce automáticamente.")
        documents = self.store.all("SELECT * FROM documents WHERE batch_id=? ORDER BY file_id", (batch_id,))
        affected, reused = [], []
        for doc in documents:
            if not doc["latest_decision"]:
                raise ValueError("Reevalúa el lote antes de preparar un cambio")
            before = self.store.one("SELECT result,payload FROM decisions WHERE id=?", (doc["latest_decision"],))
            # Deployment of new rules code is itself a dependency.
            old_code = json.loads(before["payload"])["context"].get("code_sha256")
            changed = self._change_dependencies(doc, kind, old) != self._change_dependencies(doc, kind, new) or old_code != self.code_sha256
            if changed:
                after = self.evaluation(doc, overrides={key: new_id})
                affected.append({"id": doc["id"], "file_id": doc["file_id"], "before": before["result"],
                                 "after": after["result"], "questions": after["questions"],
                                 "human_response_stale": after.get("human_response_stale", False)})
            else:
                reused.append({"id": doc["id"], "file_id": doc["file_id"], "decision_id": doc["latest_decision"]})
        change_id = secrets.token_hex(10)
        plan = {"id": change_id, "batch_id": batch_id, "kind": kind, "old_id": old_id, "new_id": new_id,
                "actor": clean(actor), "reason": clean(reason), "affected": affected, "reused": reused,
                "guard": self._change_guard(batch_id), "rules_changed": rules_changed,
                "rules_ack": bool(rules_ack), "created": now(), "ocr_reused": len(documents)}
        with self.store.connect() as db:
            db.execute("INSERT INTO source_changes(id,batch_id,kind,old_id,new_id,payload,created) VALUES(?,?,?,?,?,?,?)",
                       (change_id, batch_id, kind, old_id, new_id, canonical(plan), now()))
            self.store.event("source_change_previewed", {"change_id": change_id, "kind": kind,
                              "affected": len(affected), "reused": len(reused)}, batch_id=batch_id, db=db)
        return plan

    def prepare_upload(self, batch_id, path, kind, actor, reason, rules_ack=False):
        path = Path(path)
        if kind == "master":
            payload = read_master(path)
            payload["blob"] = str(self.store.blob(path.read_bytes(), ".xlsx"))
        elif kind == "policy":
            payload = validate_policy(json.loads(path.read_text()))
            payload["approved_by"] = clean(actor)
        else:
            raise ValueError("Carga un Excel maestro o una política JSON")
        new_id = self.store.put_source(kind, payload)
        return self.preview_source(batch_id, kind, new_id, actor, reason, rules_ack)

    def prepare_erp(self, batch_id, url, user, password, actor, reason):
        self.batch(batch_id)
        started = time.monotonic()
        client = ERPClient(url, user, password, callback=lambda k,p: self.store.event(k,p,batch_id=batch_id))
        try:
            snapshot = client.snapshot()
            source_id = self.store.put_source("erp", snapshot)
            self.store.cost("erp_preview", time.monotonic()-started, batch_id=batch_id,
                            payload={"attempts": client.attempts, "retries": client.retries})
            return self.preview_source(batch_id, "erp", source_id, actor, reason)
        except Exception as exc:
            self.store.event("source_preview_failed", {"error": str(exc), "kind": "erp"}, batch_id=batch_id)
            raise
        finally:
            client.close()

    def commit_source(self, change_id):
        row = self.store.one("SELECT * FROM source_changes WHERE id=?", (change_id,))
        if not row or row["status"] != "PREVIEW":
            raise ValueError("Este cambio no está pendiente de confirmación")
        plan = json.loads(row["payload"])
        batch_id = plan["batch_id"]
        if plan["guard"] != self._change_guard(batch_id):
            raise ValueError("Las fuentes o las respuestas han cambiado. Vuelve a previsualizar")
        key = {"master": "master_id", "erp": "snapshot_id", "policy": "policy_id"}[plan["kind"]]
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(f"UPDATE batches SET {key}=? WHERE id=?", (plan["new_id"], batch_id))
            for doc in plan["affected"]:
                db.execute("UPDATE documents SET latest_decision=NULL,state='EXTRACTED' WHERE id=?", (doc["id"],))
                self.store.event("source_change_requires_review", {"change_id": change_id, "before": doc["before"], "expected": doc["after"]}, doc["id"], batch_id, db)
            for doc in plan["reused"]:
                self.store.event("decision_reused", {"change_id": change_id, "decision_id": doc["decision_id"],
                    "old_source": plan["old_id"], "new_source": plan["new_id"], "basis": "same_relevant_dependencies"}, doc["id"], batch_id, db)
            db.execute("UPDATE source_changes SET status='APPLIED' WHERE id=?", (change_id,))
            self.store.event("source_change_applied", {k: plan[k] for k in ("id","kind","old_id","new_id","actor","reason","rules_ack")}, batch_id=batch_id, db=db)
        # A crash here leaves affected documents pending, never falsely final. Recovery is evaluate.
        self.evaluate_batch(batch_id, [d["id"] for d in plan["affected"]])
        return plan

    def source_workspace(self, batch_id):
        batch = self.batch(batch_id)
        return {"batch": batch, "master": self.store.source(batch["master_id"]),
                "policy": self.store.source(batch["policy_id"]),
                "snapshot": self.store.source(batch["snapshot_id"]) if batch["snapshot_id"] else None,
                "changes": [dict(r, plan=json.loads(r["payload"])) for r in self.store.all(
                    "SELECT * FROM source_changes WHERE batch_id=? ORDER BY created DESC", (batch_id,))]}

    def consultation_drafts(self, batch_id=None):
        """Communication aid only: grouping never authorizes bulk payment/correction."""
        from .presentation import decorate_dashboard
        data = decorate_dashboard(self, self.dashboard(batch_id))
        batches = {b["id"]: b["name"] for b in data["batches"]}
        groups = {}
        for doc in data["documents"]:
            if doc["result"] != "ESCALAR":
                continue
            key = digest({"nif":doc["nif"] or doc["id"], "batch": batch_id})[:16]
            group = groups.setdefault(key, {"id":key, "supplier":doc["supplier"], "nif":doc["nif"], "documents":[], "questions":{}})
            group["documents"].append({"id":doc["id"], "file_id":doc["file_id"], "batch":batches[doc["batch_id"]]})
            for question in doc["questions"]:
                group["questions"].setdefault(question, []).append(doc["file_id"])
        for group in groups.values():
            lines = ["BORRADOR PARA REVISAR — NO ENVIADO", "",
                     "Asunto: Información pendiente para conciliar facturas — " + group["supplier"], "", "Hola,", "",
                     "Necesitamos aclarar estos puntos antes de cerrar la conciliación:", ""]
            for question, files in group["questions"].items():
                lines.extend(["• " + question, "  Facturas: " + ", ".join(files), ""])
            lines.extend(["Expedientes incluidos:"] + ["- " + d["file_id"] + " (" + d["batch"] + ")" for d in group["documents"]])
            lines.extend(["", "Por favor, indicad la referencia o documentación que respalda la aclaración.",
                          "Este mensaje no autoriza pagos ni cambios de cuenta.", "", "Gracias,", "Administración", "",
                          "Revisión pendiente: adaptar destinatario, contexto y datos antes de enviar."])
            group["draft"] = "\n".join(lines)
        return sorted(groups.values(), key=lambda g: (-len(g["documents"]), g["supplier"]))
