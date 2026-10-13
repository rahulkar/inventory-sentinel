"""Standard operating procedures (docs/sops/*.md): what to do when Sentinel flags missing inventory.

Each SOP is Markdown with YAML front matter (schema in docs/sops/README.md): which alert types it covers, an
escalation matrix (severity x value at risk -> level, response time, who to tell) and steps, where a step can carry a
vendor-task template. The alert drill-down shows the matching SOP as a checklist, and the chat can quote it. The
"Raise vendor task" buttons and scheduled auto-proposals use the templates, always behind a person's approval.
"""
from __future__ import annotations

import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from app import config
from app.schemas import Alert, AlertSop, Sop, SopEscalation, SopStep, SopSummary

MASTER_ID = "missing-inventory-response"
FALLBACK_ID = "unclear"
_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)
_lock = threading.Lock()
_cache: tuple[float, dict[str, Sop]] | None = None


def _signature(d: Path) -> float:
    return sum(p.stat().st_mtime for p in d.glob("*.md")) + len(list(d.glob("*.md"))) if d.exists() else 0.0


def parse(path: Path) -> Sop | None:
    text = path.read_text(encoding="utf-8")
    m = _FM.match(text)
    if not m:
        return None
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict) or not meta.get("id"):
        return None
    steps = [SopStep(**{**s, "id": str(s.get("id")), "evidence": s.get("evidence") or []}) for s in meta.get("steps") or []]
    return Sop(
        id=str(meta["id"]), title=str(meta.get("title") or meta["id"]), version=str(meta.get("version") or "1"), applies_to=[str(x) for x in meta.get("applies_to") or []],
        parent=meta.get("parent"), owner_role=meta.get("owner_role"), summary=meta.get("summary"), escalation=meta.get("escalation") or [], steps=steps,
        closure=[str(x) for x in meta.get("closure") or []], triage_mapping={str(k): str(v) for k, v in (meta.get("triage_mapping") or {}).items()}, body=m.group(2).strip(),
    )


def load() -> dict[str, Sop]:
    global _cache
    d = config.SOPS_DIR
    sig = _signature(d)
    with _lock:
        if _cache and _cache[0] == sig:
            return _cache[1]
        out: dict[str, Sop] = {}
        for p in sorted(d.glob("*.md")) if d.exists() else []:
            if p.name.lower() == "readme.md":
                continue
            try:
                sop = parse(p)
            except (yaml.YAMLError, ValueError) as exc:
                print(f"[sops] skipped {p.name}: {exc}")
                continue
            if sop is not None:
                out[sop.id] = sop
        _cache = (sig, out)
        return out


def list_sops() -> list[SopSummary]:
    return [SopSummary(**s.model_dump(include=set(SopSummary.model_fields))) for s in load().values()]


def get(sop_id: str) -> Sop:
    sop = load().get(sop_id)
    if sop is None:
        raise LookupError(f"SOP {sop_id!r} not found. Known: {', '.join(load())}.")
    return sop


def sop_id_for_type(likely_type: str | None) -> str | None:
    sops = load()
    for s in sops.values():
        if likely_type and likely_type in s.applies_to:
            return s.id
    return FALLBACK_ID if FALLBACK_ID in sops else (MASTER_ID if MASTER_ID in sops else None)


def step(sop_id: str, step_id: str) -> dict[str, Any] | None:
    sop = load().get(sop_id)
    if sop is None:
        return None
    for s in sop.steps:
        if s.id == step_id:
            return s.model_dump()
    return None


# ---------------------------------------------------------------- filling templates from an alert
def alert_fields(a: Alert) -> dict[str, Any]:
    from app.assistant.plain_language import TYPE_LABEL

    return {
        **a.model_dump(), "likely_label": TYPE_LABEL.get(a.likely_type, a.likely_type.replace("_", " ")), "reasons": "; ".join(a.reasons[:3]) or "see the drill-down",
        "value_at_risk_gbp": f"{a.value_at_risk_gbp:,.0f}", "p_true_pct": f"{a.p_true:.0%}",
    }


def fill(template: str, fields: dict[str, Any]) -> str:
    safe = defaultdict(str, {k: v for k, v in fields.items()})
    try:
        return str(template).format_map(safe)
    except (ValueError, IndexError):
        return str(template)


def escalation_for(a: Alert, master: Sop | None) -> SopEscalation | None:
    rules = (master.escalation if master else []) or []
    for r in rules:
        sev = r.get("severities") or r.get("severity") or []
        if sev and a.severity not in sev:
            continue
        if a.value_at_risk_gbp < float(r.get("min_value_gbp") or 0):
            continue
        return SopEscalation(level=str(r.get("level")), label=str(r.get("label") or r.get("level")), response_hours=r.get("response_hours"), notify=[str(x) for x in r.get("notify") or []])
    return None


def for_alert(run_id: str, alert_id: str) -> AlertSop:
    from app.services import connectors, detection, storage, vendor_tasks

    a = detection.get_alert(run_id, alert_id)
    sops = load()
    if not sops:
        raise LookupError("No SOPs are installed (docs/sops is empty).")
    sop = sops.get(sop_id_for_type(a.likely_type) or "") or next(iter(sops.values()))
    master = sops.get(sop.parent or MASTER_ID) or sops.get(MASTER_ID)
    fields = alert_fields(a)
    raised = vendor_tasks.for_alert(a.alert_key)
    steps = []
    for s in sop.steps:
        d = s.model_dump()
        d["text"] = fill(s.text, fields)
        if s.vendor_task:
            d["vendor_task"] = {**s.vendor_task, "title": fill(s.vendor_task.get("title", ""), {**fields, "type_label": str(s.vendor_task.get("type", "")).replace("_", " ").capitalize()})}
        d["raised"] = [t for t in raised if t.sop_step == s.id or (s.vendor_task and t.type == s.vendor_task.get("type"))]
        steps.append(SopStep(**d))
    rd = storage.load_run(run_id)
    meta = storage.get_dataset_meta(rd.run.dataset_id)
    conn_id = (meta.params or {}).get("connector_id") if meta else None
    caps: dict[str, Any] = {}
    can = False
    if conn_id:
        try:
            c = connectors.get(conn_id)
            caps = c.capabilities or {}
            can = c.enabled and bool((caps.get("features") or {}).get("tasks", True))
        except LookupError:
            conn_id = None
    return AlertSop(
        alert=a, sop=sop, parent=SopSummary(**master.model_dump(include=set(SopSummary.model_fields))) if master and master.id != sop.id else None,
        escalation=escalation_for(a, master), steps=steps, connector_id=conn_id, can_raise_tasks=can, task_types=list(caps.get("task_types") or []),
    )
