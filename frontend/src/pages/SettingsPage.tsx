import { useEffect, useState } from "react";
import { api } from "../api";
import { useAssistant } from "../assistant/AssistantContext";
import { errorMessage, useApp } from "../context";
import { Help, Spinner } from "../components/Layout";
import { TechnicalDetails } from "../components/TechnicalDetails";
import type { LlmSettingsOut, LlmTestResult } from "../types";

export function SettingsPage() {
  const { toast } = useApp();
  const { refreshStatus, status } = useAssistant();
  const [saved, setSaved] = useState<LlmSettingsOut | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [temperature, setTemperature] = useState(0.2);
  const [timeoutS, setTimeoutS] = useState(120);
  const [streaming, setStreaming] = useState(true);
  const [agentMode, setAgentMode] = useState<"team" | "single">("team");
  const [priceIn, setPriceIn] = useState(0);
  const [priceOut, setPriceOut] = useState(0);
  const [verifySsl, setVerifySsl] = useState(false);
  const [caBundle, setCaBundle] = useState("");
  const [test, setTest] = useState<LlmTestResult | null>(null);
  const [busy, setBusy] = useState<"connect" | "test" | "save" | null>(null);

  useEffect(() => {
    api.settings.llm
      .get()
      .then((s) => {
        setSaved(s);
        setBaseUrl(s.base_url);
        setModel(s.model);
        setTemperature(s.temperature);
        setTimeoutS(s.timeout_s);
        setStreaming(s.streaming);
        setAgentMode(s.agent_mode);
        setPriceIn(s.price_input_per_m);
        setPriceOut(s.price_output_per_m);
        setVerifySsl(s.verify_ssl);
        setCaBundle(s.ca_bundle);
        if (s.model) setModels([s.model]);
      })
      .catch((e) => toast(errorMessage(e), "error"));
  }, [toast]);

  const connect = async () => {
    setBusy("connect");
    setTest(null);
    try {
      const r = await api.settings.llm.test({ base_url: baseUrl, api_key: apiKey || undefined, model: null, verify_ssl: verifySsl, ca_bundle: caBundle });
      setTest(r);
      if (r.ok) {
        setModels(r.models);
        if (!model || !r.models.includes(model)) setModel(r.models[0] ?? "");
        toast(`Connected: ${r.models.length} models available`, "success");
      }
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  const runTest = async () => {
    setBusy("test");
    try {
      const r = await api.settings.llm.test({ base_url: baseUrl, api_key: apiKey || undefined, model, verify_ssl: verifySsl, ca_bundle: caBundle });
      setTest(r);
      if (r.models.length) setModels(r.models);
      toast(r.chat_ok ? `Chat OK in ${r.latency_ms} ms` : r.error ?? "Test failed", r.chat_ok ? "success" : "error");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    setBusy("save");
    try {
      const s = await api.settings.llm.put({ base_url: baseUrl, api_key: apiKey, model, temperature, timeout_s: timeoutS, streaming, agent_mode: agentMode, price_input_per_m: priceIn, price_output_per_m: priceOut, verify_ssl: verifySsl, ca_bundle: caBundle });
      setSaved(s);
      setApiKey("");
      await refreshStatus();
      toast("Settings saved; the assistant will use them on the next message", "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p>Connect the assistant to the lab's LiteLLM gateway. The secret key is stored on this machine only and never shown again in full.</p>
        </div>
        <span className={`chip ${status?.configured ? "status-done" : "neutral"}`}>{status?.configured ? `AI connected · ${status.model}` : "AI not configured"}</span>
      </div>
      <div className="grid grid-side" style={{ gridTemplateColumns: "minmax(0, 1fr) 380px" }}>
        <div className="card">
          <div className="card-title">
            <h3>AI gateway (LiteLLM)</h3>
          </div>
          <div className="stack" style={{ gap: 12 }}>
            <label className="field">
              <span>
                Gateway URL <Help text="The LiteLLM endpoint the lab provides, e.g. https://llm.lab.example.com. With or without /v1." />
              </span>
              <input type="text" value={baseUrl} placeholder="https://gateway.example.com" onChange={(e) => setBaseUrl(e.target.value)} />
            </label>
            <label className="field">
              <span>
                Secret key <Help text="Sent as Authorization: Bearer <key>. Leave blank to keep the stored key." />
              </span>
              <input type="password" value={apiKey} placeholder={saved?.has_key ? `stored: ${saved.api_key_masked} (leave blank to keep)` : "sk-…"} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
            </label>
            <label className="check">
              <input type="checkbox" checked={verifySsl} onChange={(e) => setVerifySsl(e.target.checked)} />
              Verify the gateway's TLS certificate <span className="small muted">— off by default for lab gateways with self-signed certificates; switch on for a production gateway</span>
            </label>
            {verifySsl ? (
              <label className="field">
                <span>
                  CA bundle (optional) <Help text="Path on this machine to a PEM file with your organisation's root/intermediate certificates. Used instead of the system store when set; leave blank for public certificates." />
                </span>
                <input type="text" value={caBundle} placeholder="C:\\certs\\corp-ca.pem" onChange={(e) => setCaBundle(e.target.value)} />
              </label>
            ) : null}
            {!verifySsl && baseUrl.startsWith("https://") ? <div className="small muted">Certificate verification is off, so the HTTPS connection is not checked against a trusted certificate. Fine on the lab network; switch it on with a CA bundle for production.</div> : null}
            {saved?.tls_from_env ? <div className="small muted">TLS choice also set by the environment ({saved.tls_from_env}); the environment fills in whatever is left at the default here.</div> : null}
            <div className="row">
              <button className="btn" disabled={!baseUrl || busy !== null} onClick={connect}>
                {busy === "connect" ? <Spinner /> : null} Connect and list models
              </button>
              <span className="small muted">{models.length ? `${models.length} model${models.length === 1 ? "" : "s"} from the gateway` : "press Connect to fetch the model list"}</span>
            </div>
            <label className="field">
              Model
              {models.length ? (
                <select value={model} onChange={(e) => setModel(e.target.value)}>
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input type="text" value={model} placeholder="model id as listed by the gateway" onChange={(e) => setModel(e.target.value)} />
              )}
            </label>
            <div className="form-grid">
              <label className="field">
                <span>
                  Temperature <span className="hint">· {temperature.toFixed(2)}</span>
                </span>
                <input type="range" min={0} max={1} step={0.05} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
              </label>
              <label className="field">
                Timeout (seconds)
                <input type="number" min={10} max={600} value={timeoutS} onChange={(e) => setTimeoutS(Number(e.target.value))} />
              </label>
              <label className="check">
                <input type="checkbox" checked={streaming} onChange={(e) => setStreaming(e.target.checked)} />
                Stream answers <span className="small muted">— switch off if the model mis-streams tool calls</span>
              </label>
              <label className="field">
                <span>
                  Agent mode <Help text="Team: a front-door agent routes to five specialists. Single: one agent with every tool; more robust with weaker models." />
                </span>
                <select value={agentMode} onChange={(e) => setAgentMode(e.target.value as "team" | "single")}>
                  <option value="team">Team of specialists (recommended)</option>
                  <option value="single">Single agent</option>
                </select>
              </label>
              <label className="field">
                <span>
                  Price per 1M input tokens (USD) <Help text="Leave 0 to use the price the gateway reports (LiteLLM /model/info) or litellm's bundled price list. Set both to override." />
                </span>
                <input type="number" min={0} step={0.01} value={priceIn} onChange={(e) => setPriceIn(Number(e.target.value))} />
              </label>
              <label className="field">
                <span>Price per 1M output tokens (USD)</span>
                <input type="number" min={0} step={0.01} value={priceOut} onChange={(e) => setPriceOut(Number(e.target.value))} />
              </label>
            </div>
            <div className="row">
              <button className="btn" disabled={!baseUrl || !model || busy !== null} onClick={runTest}>
                {busy === "test" ? <Spinner /> : null} Test connection
              </button>
              <button className="btn primary" disabled={!baseUrl || !model || busy !== null} onClick={save}>
                {busy === "save" ? <Spinner /> : null} Save
              </button>
              {saved?.updated_at ? <span className="small muted">last saved {saved.updated_at.replace("T", " ")}</span> : null}
            </div>
            {test ? (
              <div className={`alert ${test.ok && (test.chat_ok || !model) ? "info" : "error"}`}>
                {test.error ? test.error : test.chat_ok ? `Connected. ${test.models.length} models listed; test reply “${test.reply}” in ${test.latency_ms} ms.` : `Connected. ${test.models.length} models listed.`}
              </div>
            ) : null}
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <div className="card-title">
              <h3>Status</h3>
            </div>
            <dl className="kv">
              <dt>Assistant</dt>
              <dd>{status ? (status.available ? "available" : `unavailable: ${status.reason}`) : "–"}</dd>
              <dt>Gateway</dt>
              <dd>{status?.base_host || "not set"}</dd>
              <dt>Model</dt>
              <dd>{status?.model || "not set"}</dd>
              <dt>Mode</dt>
              <dd>{status ? `${status.agent_mode}, ${status.streaming ? "streaming" : "no streaming"}` : "–"}</dd>
              <dt>Engine</dt>
              <dd>{status?.engine_ready ? "warm" : "builds on first message"}</dd>
              {status?.last_error ? (
                <>
                  <dt>Last error</dt>
                  <dd className="small" style={{ color: "var(--critical)" }}>{status.last_error}</dd>
                </>
              ) : null}
              <dt>Packages</dt>
              <dd className="small mono">{status ? Object.entries(status.versions).map(([k, v]) => `${k} ${v ?? "–"}`).join(" · ") : "–"}</dd>
            </dl>
          </div>
          <div className="card">
            <div className="card-title">
              <h3>How the assistant works</h3>
            </div>
            <ul className="muted small" style={{ paddingLeft: 18, margin: 0 }}>
              <li>Every message goes to a front-door agent that answers directly or hands over to a specialist: data analyst, model analyst, alert investigator, loss-prevention planner or explainer.</li>
              <li>Agents read live app data through tools (datasets, models, detection runs, alerts, drill-downs, the investigation planner, triage feedback, the user guide) and see the page, tab, alert and item you have open.</li>
              <li>Anything that creates or changes something becomes a proposal card you confirm before it runs.</li>
              <li>All model calls go through the gateway above; nothing else is contacted.</li>
            </ul>
            <TechnicalDetails title="Use the tools from other agents (MCP)">
              <div className="small muted">
                The same tool catalogue is served as an MCP server at <code>{`${window.location.origin}/mcp/`}</code> (streamable HTTP). For Claude Desktop add a server with the command:
              </div>
              <pre className="code-block">{`npx mcp-remote ${window.location.origin}/mcp/`}</pre>
              <div className="small muted">Resources: sentinel://guide, sentinel://readme, sentinel://glossary, sentinel://story.</div>
            </TechnicalDetails>
          </div>
        </div>
      </div>
    </div>
  );
}
