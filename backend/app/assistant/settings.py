"""LLM gateway settings: stored server-side in data/settings.json, key never returned to the browser."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app import config
from app.services import storage


class LlmSettings(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = Field(0.2, ge=0, le=2)
    timeout_s: int = Field(config.ASSISTANT_TIMEOUT_S, ge=10, le=600)
    streaming: bool = True
    agent_mode: Literal["team", "single"] = "team"
    embedding_model: str = ""  # optional: a gateway embedding model for semantic document search; blank = keyword search only
    price_input_per_m: float = Field(0.0, ge=0)  # USD per 1M prompt tokens; 0 = use the gateway's or litellm's price list
    price_output_per_m: float = Field(0.0, ge=0)  # USD per 1M completion tokens; 0 = automatic
    verify_ssl: bool = False  # off by default: lab gateways usually carry self-signed certificates; switch on (with a CA bundle) for production
    ca_bundle: str = ""  # optional path to a PEM bundle that signs the gateway's certificate (corporate CA)
    updated_at: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def fingerprint(self) -> str:
        return json.dumps(self.model_dump(exclude={"updated_at"}), sort_keys=True)


class LlmSettingsOut(BaseModel):
    base_url: str
    model: str
    temperature: float
    timeout_s: int
    streaming: bool
    agent_mode: str
    embedding_model: str
    price_input_per_m: float
    price_output_per_m: float
    verify_ssl: bool
    ca_bundle: str
    tls_from_env: str | None  # which environment variable (if any) decided the TLS choice
    updated_at: str | None
    api_key_masked: str
    has_key: bool
    configured: bool


class LlmTestRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    verify_ssl: bool | None = None
    ca_bundle: str | None = None


class LlmTestResult(BaseModel):
    ok: bool
    models: list[str] = []
    chat_ok: bool = False
    reply: str | None = None
    latency_ms: int | None = None
    error: str | None = None


_cache: tuple[float, LlmSettings] | None = None
MASK_PREFIX = "••••"
FALSY = {"0", "false", "no", "off"}


def env_tls() -> tuple[bool | None, str, str | None]:
    """Deployment-time TLS choice, same convention as the lab's other projects.

    LITELLM_SSL_VERIFY=true/false switches certificate verification on or off; LITELLM_CA_BUNDLE, SSL_CERT_FILE or
    REQUESTS_CA_BUNDLE name a PEM bundle. Returns (verify, bundle_path, source): verify is None when the variable is unset.
    """
    raw = os.environ.get("LITELLM_SSL_VERIFY", "").strip().lower()
    verify = (raw not in FALSY) if raw else None
    for var in ("LITELLM_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        path = os.environ.get(var, "").strip()
        if path:
            return verify, path, (f"LITELLM_SSL_VERIFY={raw}" if raw else var)
    return verify, "", (f"LITELLM_SSL_VERIFY={raw}" if raw else None)


def apply_env_tls(settings: LlmSettings) -> LlmSettings:
    """Environment variables fill in what Settings leaves at the default (verification off, no bundle)."""
    verify, bundle, _ = env_tls()
    if verify and not settings.verify_ssl:
        settings.verify_ssl = True
    if bundle:
        if not settings.ca_bundle:
            settings.ca_bundle = bundle
        settings.verify_ssl = True  # a bundle only makes sense with verification on
    return settings


def normalise_base_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    u = u.rstrip("/")
    for suffix in ("/v1", "/chat/completions", "/v1/chat/completions"):
        if u.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
    return u


def mask(key: str) -> str:
    if not key:
        return ""
    return MASK_PREFIX + key[-4:] if len(key) > 4 else MASK_PREFIX


def is_masked(value: str | None) -> bool:
    return value is None or value == "" or value.startswith(MASK_PREFIX) or value.strip("*") == ""


def load() -> LlmSettings:
    global _cache
    path = config.SETTINGS_PATH
    mtime = path.stat().st_mtime if path.exists() else -1.0
    if _cache and _cache[0] == mtime:
        return _cache[1]
    settings = LlmSettings()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            settings = LlmSettings(**(data.get("llm") or {}))
        except (ValueError, TypeError):
            settings = LlmSettings()
    settings = apply_env_tls(settings)
    _cache = (mtime, settings)
    return settings


def save(settings: LlmSettings) -> LlmSettings:
    global _cache
    config.ensure_dirs()
    settings.updated_at = storage.now_iso()
    storage.atomic_write_text(config.SETTINGS_PATH, json.dumps({"llm": settings.model_dump()}, indent=1))
    _cache = None
    return load()


def merge_put(existing: LlmSettings, incoming: dict[str, Any]) -> LlmSettings:
    data = existing.model_dump()
    for k, v in incoming.items():
        if k not in data or k == "updated_at":
            continue
        if k == "api_key":
            if is_masked(v):
                continue  # blank or masked keeps the stored key
            data[k] = str(v).strip()
        elif k == "base_url":
            data[k] = normalise_base_url(str(v))
        else:
            data[k] = v
    return LlmSettings(**data)


def to_out(s: LlmSettings) -> LlmSettingsOut:
    return LlmSettingsOut(
        base_url=s.base_url,
        model=s.model,
        temperature=s.temperature,
        timeout_s=s.timeout_s,
        streaming=s.streaming,
        agent_mode=s.agent_mode,
        embedding_model=s.embedding_model,
        price_input_per_m=s.price_input_per_m,
        price_output_per_m=s.price_output_per_m,
        verify_ssl=s.verify_ssl,
        ca_bundle=s.ca_bundle,
        tls_from_env=env_tls()[2],
        updated_at=s.updated_at,
        api_key_masked=mask(s.api_key),
        has_key=bool(s.api_key),
        configured=s.configured,
    )


# ---------------------------------------------------------------- gateway probes
def verify_arg(verify_ssl: bool, ca_bundle: str = "") -> bool | str:
    """What httpx/litellm should verify against: a CA bundle path when given, else the on/off switch."""
    path = (ca_bundle or "").strip()
    return path if path else bool(verify_ssl)


def _headers(api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def readable_error(exc: Exception, base_url: str) -> str:
    host = base_url.split("//", 1)[-1].split("/", 1)[0] or base_url
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        body = ""
        try:
            body = exc.response.json().get("error", {}).get("message") or exc.response.text[:200]
        except Exception:  # noqa: BLE001
            body = exc.response.text[:200]
        if code in (401, 403):
            return f"The gateway rejected the key (HTTP {code}). {body}".strip()
        if code == 404:
            low = body.lower()
            if "model" in low and ("not found" in low or "no longer available" in low or "does not exist" in low):
                return f"The gateway could not serve this model (HTTP 404). Pick another model from the list. Detail: {body[:300]}"
            return f"Not found (HTTP 404) at {exc.request.url.path}: is this an OpenAI-compatible LiteLLM endpoint? {body[:300]}".strip()
        if code == 429:
            return f"The gateway is rate-limiting requests (HTTP 429). {body}".strip()
        return f"The gateway returned HTTP {code}. {body}".strip()
    low = str(exc).lower()
    if "certificate" in low or "ssl" in low or "tls" in low:
        return f"The certificate of {host} is not trusted ({str(exc)[:120]}). In Settings, give the path to your organisation's CA bundle, or switch certificate verification off (the default for lab gateways)."
    if isinstance(exc, httpx.ConnectError):
        return f"Cannot reach {host}. Check the URL, VPN or proxy."
    if isinstance(exc, httpx.TimeoutException):
        return f"Timed out talking to {host}."
    return f"{type(exc).__name__}: {exc}"


async def list_models(base_url: str, api_key: str, timeout: float = 15.0, verify: bool | str = False) -> list[str]:
    base = normalise_base_url(base_url)
    async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
        r = await client.get(f"{base}/v1/models", headers=_headers(api_key))
        r.raise_for_status()
        data = r.json()
    items = data.get("data", data if isinstance(data, list) else [])
    ids = []
    for it in items:
        mid = it.get("id") if isinstance(it, dict) else str(it)
        if mid:
            ids.append(str(mid))
    return sorted(set(ids))


async def probe(base_url: str, api_key: str, model: str | None, want_chat: bool = True, timeout: float = 30.0, verify: bool | str = False) -> LlmTestResult:
    base = normalise_base_url(base_url)
    if not base:
        return LlmTestResult(ok=False, error="Enter the gateway URL first.")
    t0 = time.perf_counter()
    try:
        models = await list_models(base, api_key, timeout=min(timeout, 15.0), verify=verify)
    except Exception as exc:  # noqa: BLE001
        return LlmTestResult(ok=False, error=readable_error(exc, base))
    result = LlmTestResult(ok=True, models=models, latency_ms=int((time.perf_counter() - t0) * 1000))
    if not want_chat or not model:
        if want_chat and not model:
            result.error = "Pick a model to test a chat call."
        return result
    if models and model not in models:
        result.ok = False
        result.error = f"Model '{model}' is not in the gateway's model list."
        return result
    try:
        t1 = time.perf_counter()
        async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
            r = await client.post(
                f"{base}/v1/chat/completions",
                headers=_headers(api_key),
                # Reasoning models (e.g. Gemini 3.x) may spend the whole budget thinking, so give them room
                # and treat an HTTP 200 with an empty message as a successful round trip.
                json={"model": model, "messages": [{"role": "user", "content": "Reply with exactly: OK"}], "max_tokens": 256, "temperature": 0},
            )
            r.raise_for_status()
            data = r.json()
        choice = (data.get("choices") or [{}])[0]
        reply = (choice.get("message") or {}).get("content") or ""
        result.chat_ok = True
        result.reply = str(reply).strip()[:80] or "(empty text, but the model answered: finish_reason=%s)" % choice.get("finish_reason")
        result.latency_ms = int((time.perf_counter() - t1) * 1000)
    except Exception as exc:  # noqa: BLE001
        result.ok = False
        result.chat_ok = False
        result.error = readable_error(exc, base)
    return result
