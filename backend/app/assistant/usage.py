"""Token, cost and invocation accounting for the assistant.

Every LLM call made by an agent is recorded (agent, model, tokens, cost) in data/assistant_usage.json, together
with the tool calls it produced. Prices come, in order, from the Settings override, the gateway's own price list
(LiteLLM /model/info), litellm's bundled price map, or are unknown (cost shown as "n/a").
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from app import config
from app.services import storage

_lock = threading.Lock()
_state: dict[str, Any] | None = None
_price_cache: dict[str, dict[str, Any]] = {}  # "base|model" -> {"input": $/token, "output": $/token, "source": ...}

AGENT_LABELS = {
    "sentinel_assistant": "Front door",
    "data_analyst": "Data analyst",
    "model_analyst": "Model analyst",
    "alert_investigator": "Alert investigator",
    "lp_planner": "Loss-prevention planner",
    "explainer": "Explainer",
}


# ---------------------------------------------------------------- persistence
def _empty() -> dict[str, Any]:
    return {"records": [], "archived": {"llm_calls": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "thoughts_tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0, "turns": 0}, "since": storage.now_iso()}


def _load() -> dict[str, Any]:
    global _state
    if _state is not None:
        return _state
    path = config.ASSISTANT_USAGE_PATH
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("records"), list):
                base = _empty()
                base.update(data)
                _state = base
                return _state
        except (ValueError, OSError):
            pass
    _state = _empty()
    return _state


def _save(state: dict[str, Any]) -> None:
    config.ensure_dirs()
    storage.atomic_write_text(config.ASSISTANT_USAGE_PATH, json.dumps(state))


def reset() -> None:
    global _state
    with _lock:
        _state = _empty()
        _save(_state)


# ---------------------------------------------------------------- pricing
def _price_key(base_url: str, model: str) -> str:
    return f"{base_url}|{model}"


def set_gateway_prices(base_url: str, prices: dict[str, tuple[float | None, float | None]]) -> None:
    """Remember per-token prices reported by the gateway's /model/info."""
    for model, (inp, out) in prices.items():
        if inp is None and out is None:
            continue
        _price_cache[_price_key(base_url, model)] = {"input": inp or 0.0, "output": out or 0.0, "source": "gateway"}


async def fetch_gateway_prices(base_url: str, api_key: str, timeout: float = 8.0, verify: bool | str = False) -> int:
    """LiteLLM proxies expose /model/info with input/output cost per token. Best effort; returns how many were stored."""
    import httpx

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
            r = await client.get(f"{base_url}/model/info", headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception:  # noqa: BLE001
        return 0
    found: dict[str, tuple[float | None, float | None]] = {}
    for item in data.get("data", []) if isinstance(data, dict) else []:
        name = item.get("model_name")
        info = item.get("model_info") or {}
        if name:
            found[str(name)] = (info.get("input_cost_per_token"), info.get("output_cost_per_token"))
    set_gateway_prices(base_url, found)
    return len([v for v in found.values() if v[0] is not None or v[1] is not None])


def _litellm_price(model: str) -> dict[str, Any] | None:
    import sys

    if "litellm" not in sys.modules:
        return None  # never import litellm from a worker thread (its logging filter wedges the loop); the engine imports it first
    try:
        import litellm

        for key in (model, f"gemini/{model}", f"openai/{model}", f"anthropic/{model}", f"vertex_ai/{model}", f"azure/{model}"):
            v = litellm.model_cost.get(key)
            if v and (v.get("input_cost_per_token") is not None or v.get("output_cost_per_token") is not None):
                return {"input": float(v.get("input_cost_per_token") or 0.0), "output": float(v.get("output_cost_per_token") or 0.0), "source": "litellm price list"}
    except Exception:  # noqa: BLE001
        return None
    return None


def resolve_price(base_url: str, model: str, settings_in_per_m: float = 0.0, settings_out_per_m: float = 0.0) -> dict[str, Any]:
    """Return {"input": $/token, "output": $/token, "source": str, "known": bool}."""
    if settings_in_per_m > 0 or settings_out_per_m > 0:
        return {"input": settings_in_per_m / 1e6, "output": settings_out_per_m / 1e6, "source": "settings override", "known": True}
    hit = _price_cache.get(_price_key(base_url, model))
    if hit:
        return {**hit, "known": True}
    lp = _litellm_price(model)
    if lp:
        return {**lp, "known": True}
    return {"input": 0.0, "output": 0.0, "source": "unknown", "known": False}


# ---------------------------------------------------------------- recording
def _is_chat(r: dict[str, Any]) -> bool:
    return r.get("kind", "chat") == "chat"


def _append(rec: dict[str, Any]) -> None:
    """Store one record; past the cap the oldest are folded into the archived counters."""
    with _lock:
        state = _load()
        state["records"].append(rec)
        if len(state["records"]) > config.ASSISTANT_USAGE_CAP:
            drop = state["records"][: len(state["records"]) - config.ASSISTANT_USAGE_CAP]
            state["records"] = state["records"][len(drop) :]
            a = state["archived"]
            a["turns"] += len({(r["session_id"], r["turn_id"]) for r in drop if _is_chat(r)})
            for r in drop:
                if not _is_chat(r):
                    a["embedding_calls"] = a.get("embedding_calls", 0) + 1
                    a["embedding_tokens"] = a.get("embedding_tokens", 0) + r["prompt_tokens"]
                    a["embedding_cost_usd"] = a.get("embedding_cost_usd", 0.0) + (r["cost_usd"] or 0.0)
                    continue
                a["llm_calls"] += 1
                a["tool_calls"] += len(r["tool_calls"])
                a["prompt_tokens"] += r["prompt_tokens"]
                a["completion_tokens"] += r["completion_tokens"]
                a["thoughts_tokens"] += r["thoughts_tokens"]
                if r["cost_usd"] is None:
                    a["unpriced_calls"] += 1
                else:
                    a["cost_usd"] += r["cost_usd"]
        _save(state)


def record_llm_call(
    *,
    session_id: str,
    turn_id: str,
    agent: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    thoughts_tokens: int = 0,
    cached_tokens: int = 0,
    tool_calls: list[str] | None = None,
    price: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one LLM call; returns the record (with cost_usd None when the price is unknown)."""
    cost: float | None = None
    if price and price.get("known"):
        # OpenAI-style usage counts reasoning tokens inside completion_tokens, so they are billed as output here.
        cost = round(prompt_tokens * float(price["input"]) + completion_tokens * float(price["output"]), 8)
    rec = {
        "ts": time.time(),
        "session_id": session_id,
        "turn_id": turn_id,
        "agent": agent,
        "model": model,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "thoughts_tokens": int(thoughts_tokens or 0),
        "cached_tokens": int(cached_tokens or 0),
        "tool_calls": list(tool_calls or []),
        "cost_usd": cost,
    }
    _append(rec)
    return rec


def record_embedding_call(*, model: str, tokens: int, n_inputs: int, estimated: bool = False) -> None:
    """One /v1/embeddings request (document indexing or a semantic search), priced like a prompt."""
    from app.assistant import settings as llm_settings

    st = llm_settings.load()
    price = resolve_price(st.base_url, model)
    cost = round(tokens * float(price["input"]), 8) if price["known"] else None
    rec = {
        "ts": time.time(), "kind": "embedding", "session_id": "", "turn_id": "", "agent": "embeddings", "model": model,
        "prompt_tokens": int(tokens or 0), "completion_tokens": 0, "thoughts_tokens": 0, "cached_tokens": 0,
        "tool_calls": [], "cost_usd": cost, "n_inputs": int(n_inputs), "estimated": bool(estimated),
    }
    _append(rec)


# ---------------------------------------------------------------- reporting
def _agg(records: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"llm_calls": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "thoughts_tokens": 0, "cached_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0, "invocations": 0, "sessions": 0}
    turns: set[tuple[str, str]] = set()
    sessions: set[str] = set()
    for r in records:
        out["llm_calls"] += 1
        out["tool_calls"] += len(r.get("tool_calls") or [])
        out["prompt_tokens"] += r["prompt_tokens"]
        out["completion_tokens"] += r["completion_tokens"]
        out["thoughts_tokens"] += r.get("thoughts_tokens", 0)
        out["cached_tokens"] += r.get("cached_tokens", 0)
        if r.get("cost_usd") is None:
            out["unpriced_calls"] += 1
        else:
            out["cost_usd"] += r["cost_usd"]
        turns.add((r["session_id"], r["turn_id"]))
        sessions.add(r["session_id"])
    out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    out["invocations"] = len(turns)
    out["sessions"] = len(sessions)
    out["cost_usd"] = round(out["cost_usd"], 6)
    return out


def report(session_id: str | None = None, team: list[dict[str, Any]] | None = None, price: dict[str, Any] | None = None, model: str = "") -> dict[str, Any]:
    """Aggregate usage: totals, per agent (merged with the team roster), per tool, per day, recent sessions."""
    with _lock:
        state = _load()
        records = [r for r in state["records"] if _is_chat(r)]
        archived = dict(state["archived"])
        since = state.get("since")
    if session_id:
        records = [r for r in records if r["session_id"] == session_id]
        archived = None
    totals = _agg(records)
    if archived:
        for k in ("llm_calls", "tool_calls", "prompt_tokens", "completion_tokens", "thoughts_tokens", "unpriced_calls"):
            totals[k] += archived.get(k, 0)
        totals["invocations"] += archived.get("turns", 0)
        totals["total_tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
        totals["cost_usd"] = round(totals["cost_usd"] + archived.get("cost_usd", 0.0), 6)

    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_agent[r["agent"]].append(r)
    roster = {t["name"]: t for t in (team or [])}
    names = list(roster.keys()) + [n for n in by_agent if n not in roster]
    agents = []
    for name in names:
        spec = roster.get(name, {})
        stats = _agg(by_agent.get(name, []))
        agents.append(
            {
                "name": name,
                "label": spec.get("label") or AGENT_LABELS.get(name, name.replace("_", " ").title()),
                "description": spec.get("description", ""),
                "tools": spec.get("tools", []),
                "n_tools": len(spec.get("tools", [])),
                "in_team": name in roster,
                **{k: v for k, v in stats.items() if k != "sessions"},
                "share_of_cost": (stats["cost_usd"] / totals["cost_usd"]) if totals["cost_usd"] else 0.0,
            }
        )

    tool_counts: dict[str, int] = defaultdict(int)
    for r in records:
        for t in r.get("tool_calls") or []:
            tool_counts[t] += 1
    tools = sorted(({"name": k, "calls": v} for k, v in tool_counts.items()), key=lambda x: -x["calls"])

    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_day[datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d")].append(r)
    days = [{"day": d, **{k: v for k, v in _agg(rs).items() if k in ("llm_calls", "tool_calls", "total_tokens", "cost_usd", "invocations")}} for d, rs in sorted(by_day.items())][-14:]

    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_session[r["session_id"]].append(r)
    sessions = sorted(
        ({"session_id": sid, "last_ts": max(x["ts"] for x in rs), **{k: v for k, v in _agg(rs).items() if k in ("llm_calls", "tool_calls", "total_tokens", "cost_usd", "invocations")}} for sid, rs in by_session.items()),
        key=lambda x: -x["last_ts"],
    )[:10]

    p = price or {"input": 0.0, "output": 0.0, "source": "unknown", "known": False}
    return {
        "since": since,
        "session_id": session_id,
        "model": model,
        "pricing": {"model": model, "input_per_m": round(p["input"] * 1e6, 4), "output_per_m": round(p["output"] * 1e6, 4), "source": p["source"], "known": bool(p["known"]), "currency": "USD"},
        "totals": {**totals, "agents": len([a for a in agents if a["in_team"]]) or len(agents)},
        "agents": agents,
        "tools": tools,
        "by_day": days,
        "sessions": sessions,
    }


def session_totals(session_id: str) -> dict[str, Any]:
    with _lock:
        records = [r for r in _load()["records"] if r["session_id"] == session_id and _is_chat(r)]
    return {k: v for k, v in _agg(records).items() if k in ("llm_calls", "tool_calls", "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd", "unpriced_calls")}


def full_report(session_id: str | None = None) -> dict[str, Any]:
    """Report with the current team roster and price (usable from tools, MCP and the API)."""
    from app.assistant import settings as llm_settings

    st = llm_settings.load()
    try:
        from app.assistant.agents import team_roster

        team = team_roster(st.agent_mode)
    except Exception:  # noqa: BLE001
        team = [{"name": n, "label": l, "description": "", "tools": []} for n, l in AGENT_LABELS.items()]
    price = resolve_price(st.base_url, st.model, st.price_input_per_m, st.price_output_per_m) if st.model else None
    return report(session_id=session_id, team=team, price=price, model=st.model)


# ---------------------------------------------------------------- finops (Settings page)
def _spend(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cost_usd": round(sum(r["cost_usd"] or 0.0 for r in records), 6),
        "tokens": sum(r["prompt_tokens"] + r["completion_tokens"] for r in records),
        "calls": len(records),
        "unpriced_calls": sum(1 for r in records if r["cost_usd"] is None),
    }


def finops(monthly_budget_usd: float = 0.0) -> dict[str, Any]:
    """Spend by period, chat vs embeddings, per agent, per day, and the month against an optional budget."""
    import calendar

    from app.assistant import settings as llm_settings

    st = llm_settings.load()
    with _lock:
        state = _load()
        records = list(state["records"])
        archived = dict(state["archived"])
        since = state.get("since")
    now = datetime.now()
    day0 = datetime(now.year, now.month, now.day).timestamp()
    week0 = day0 - 6 * 86400
    month0 = datetime(now.year, now.month, 1).timestamp()
    chat = [r for r in records if _is_chat(r)]
    emb = [r for r in records if not _is_chat(r)]

    all_time = _spend(records)
    all_time["cost_usd"] = round(all_time["cost_usd"] + archived.get("cost_usd", 0.0) + archived.get("embedding_cost_usd", 0.0), 6)
    all_time["tokens"] += archived.get("prompt_tokens", 0) + archived.get("completion_tokens", 0) + archived.get("embedding_tokens", 0)
    all_time["calls"] += archived.get("llm_calls", 0) + archived.get("embedding_calls", 0)
    all_time["unpriced_calls"] += archived.get("unpriced_calls", 0)
    periods = {
        "today": _spend([r for r in records if r["ts"] >= day0]),
        "last_7_days": _spend([r for r in records if r["ts"] >= week0]),
        "month_to_date": _spend([r for r in records if r["ts"] >= month0]),
        "all_time": all_time,
    }

    mtd = periods["month_to_date"]["cost_usd"]
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed = (now.timestamp() - month0) / 86400
    projected = mtd / elapsed * days_in_month if elapsed >= 1 else None  # under a day of data is too little to extrapolate
    budget = {
        "monthly_usd": monthly_budget_usd,
        "month": now.strftime("%B %Y"),
        "spent_usd": mtd,
        "projected_usd": round(projected, 6) if projected is not None else None,
        "used_pct": (mtd / monthly_budget_usd) if monthly_budget_usd > 0 else None,
        "status": ("over" if mtd > monthly_budget_usd else "at_risk" if projected and projected > monthly_budget_usd else "ok") if monthly_budget_usd > 0 else "none",
    }

    turns = {(r["session_id"], r["turn_id"]) for r in chat}
    n_turns = len(turns) + archived.get("turns", 0)
    chat_agg = _agg(chat)
    chat_cost = chat_agg["cost_usd"] + archived.get("cost_usd", 0.0)
    chat_tokens = chat_agg["total_tokens"] + archived.get("prompt_tokens", 0) + archived.get("completion_tokens", 0)
    chat_calls = chat_agg["llm_calls"] + archived.get("llm_calls", 0)
    chat_out = {
        "conversations": len({r["session_id"] for r in chat}),
        "questions": n_turns,
        "llm_calls": chat_calls,
        "tool_calls": chat_agg["tool_calls"] + archived.get("tool_calls", 0),
        "tokens": chat_tokens,
        "cost_usd": round(chat_cost, 6),
        "unpriced_calls": chat_agg["unpriced_calls"] + archived.get("unpriced_calls", 0),
        "avg_cost_per_question": round(chat_cost / n_turns, 6) if n_turns else 0.0,
        "avg_tokens_per_question": round(chat_tokens / n_turns) if n_turns else 0,
        "avg_calls_per_question": round(chat_calls / n_turns, 2) if n_turns else 0.0,
    }

    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in chat:
        by_agent[r["agent"]].append(r)
    agents = sorted(
        (
            {"name": n, "label": AGENT_LABELS.get(n, n.replace("_", " ").title()), "invocations": len({(r["session_id"], r["turn_id"]) for r in rs}), **_spend(rs)}
            for n, rs in by_agent.items()
        ),
        key=lambda a: (-a["cost_usd"], -a["tokens"]),
    )

    emb_spend = _spend(emb)
    embeddings = {
        "model": st.embedding_model,
        "calls": emb_spend["calls"] + archived.get("embedding_calls", 0),
        "inputs": sum(r.get("n_inputs", 0) for r in emb),
        "tokens": emb_spend["tokens"] + archived.get("embedding_tokens", 0),
        "cost_usd": round(emb_spend["cost_usd"] + archived.get("embedding_cost_usd", 0.0), 6),
        "unpriced_calls": emb_spend["unpriced_calls"],
        "estimated_tokens": any(r.get("estimated") for r in emb),
    }

    daily: dict[str, dict[str, float]] = {}
    for i in range(29, -1, -1):
        daily[datetime.fromtimestamp(day0 - i * 86400).strftime("%Y-%m-%d")] = {"chat_usd": 0.0, "embeddings_usd": 0.0, "tokens": 0}
    for r in records:
        d = daily.get(datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d"))
        if d is None:
            continue
        d["chat_usd" if _is_chat(r) else "embeddings_usd"] += r["cost_usd"] or 0.0
        d["tokens"] += r["prompt_tokens"] + r["completion_tokens"]

    chat_price = resolve_price(st.base_url, st.model, st.price_input_per_m, st.price_output_per_m) if st.model else None
    emb_price = resolve_price(st.base_url, st.embedding_model) if st.embedding_model else None
    return {
        "since": since,
        "currency": "USD",
        "periods": periods,
        "budget": budget,
        "chat": chat_out,
        "agents": agents,
        "embeddings": embeddings,
        "daily": [{"day": k, "chat_usd": round(v["chat_usd"], 6), "embeddings_usd": round(v["embeddings_usd"], 6), "tokens": int(v["tokens"])} for k, v in daily.items()],
        "pricing": {
            "chat": {"model": st.model, "input_per_m": round(chat_price["input"] * 1e6, 4), "output_per_m": round(chat_price["output"] * 1e6, 4), "source": chat_price["source"], "known": chat_price["known"]} if chat_price else None,
            "embeddings": {"model": st.embedding_model, "input_per_m": round(emb_price["input"] * 1e6, 4), "source": emb_price["source"], "known": emb_price["known"]} if emb_price else None,
        },
    }
