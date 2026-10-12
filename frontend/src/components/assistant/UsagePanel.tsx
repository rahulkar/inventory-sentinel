import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api";
import { useAssistant } from "../../assistant/AssistantContext";
import { errorMessage, useApp } from "../../context";
import { EmptyState, TeamArt } from "../Illustrations";
import { Help } from "../Layout";
import { TechnicalDetails } from "../TechnicalDetails";
import type { UsageReport } from "../../types";
import { num } from "../../utils";

export const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
export const usd2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return num.format(n);
}

export function fmtCost(cost: number, unpriced = 0): string {
  if (unpriced && !cost) return "n/a";
  return (cost < 0.01 && cost > 0 ? usd.format(cost) : usd2.format(cost)) + (unpriced ? "+" : "");
}

/** Team roster plus invocations, tokens and cost per agent (all time or for one conversation). */
export function UsagePanel({ sessionId }: { sessionId?: string | null }) {
  const { toast, setPage } = useApp();
  const { status, streaming } = useAssistant();
  const [scope, setScope] = useState<"all" | "session">("all");
  const [report, setReport] = useState<UsageReport | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await api.assistant.usage(scope === "session" ? sessionId : null));
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setLoading(false);
    }
  }, [scope, sessionId, toast]);

  useEffect(() => {
    if (!streaming) void load();
  }, [load, streaming]);

  const reset = async () => {
    if (!confirm("Reset the usage counters? Conversations are kept; only the token and cost history is cleared.")) return;
    try {
      await api.assistant.resetUsage();
      await load();
      toast("Usage counters reset", "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  const t = report?.totals;
  const agents = report?.agents ?? [];
  const chart = agents.filter((a) => a.llm_calls > 0).map((a) => ({ label: a.label, cost: a.cost_usd, tokens: a.total_tokens }));
  const pricing = report?.pricing;
  return (
    <div className="card">
      <div className="card-title">
        <h3>
          Team and usage <Help text="Every answer is one or more calls to the gateway model. Tokens are counted from the gateway's responses; cost = prompt tokens × input price + completion tokens × output price." />
        </h3>
        <div className="row" style={{ gap: 6 }}>
          <button className={`toggle-chip ${scope === "all" ? "on" : ""}`} onClick={() => setScope("all")}>
            All time
          </button>
          <button className={`toggle-chip ${scope === "session" ? "on" : ""}`} disabled={!sessionId} onClick={() => setScope("session")} title={sessionId ? "" : "Open a conversation first"}>
            This conversation
          </button>
          <button className="btn sm" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
          <button className="btn sm" onClick={reset} disabled={loading || !t?.llm_calls}>
            Reset
          </button>
        </div>
      </div>
      {!report ? (
        <EmptyState art={<TeamArt />}>
          <b>{loading ? "Loading…" : "No usage recorded yet."}</b>
          <div className="muted small">The team's model calls, tokens and cost appear here after the first answer.</div>
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-4" style={{ marginBottom: 14 }}>
            <div className="stat">
              <div className="label">Agents</div>
              <div className="value">{t?.agents ?? agents.length}</div>
              <div className="sub">{status?.agent_mode === "single" ? "single-agent mode" : "front door + 5 specialists"}</div>
            </div>
            <div className="stat">
              <div className="label">Invocations</div>
              <div className="value">{num.format(t?.invocations ?? 0)}</div>
              <div className="sub">
                {num.format(t?.llm_calls ?? 0)} model calls · {num.format(t?.tool_calls ?? 0)} tool calls
              </div>
            </div>
            <div className="stat">
              <div className="label">Tokens</div>
              <div className="value">{fmtTokens(t?.total_tokens ?? 0)}</div>
              <div className="sub">
                {fmtTokens(t?.prompt_tokens ?? 0)} in · {fmtTokens(t?.completion_tokens ?? 0)} out
                {t?.thoughts_tokens ? ` (${fmtTokens(t.thoughts_tokens)} thinking)` : ""}
              </div>
            </div>
            <div className="stat">
              <div className="label">Estimated cost</div>
              <div className="value">{fmtCost(t?.cost_usd ?? 0, t?.unpriced_calls)}</div>
              <div className="sub">
                {pricing?.known ? `${usd.format(pricing.input_per_m)} in · ${usd.format(pricing.output_per_m)} out per 1M tokens (${pricing.source})` : "no price known for this model: set one in Settings"}
              </div>
            </div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 360 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>What it handles</th>
                  <th className="num">Tools</th>
                  <th className="num">Invocations</th>
                  <th className="num">Model calls</th>
                  <th className="num">Tool calls</th>
                  <th className="num">Tokens in / out</th>
                  <th className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.name} className={a.in_team ? "" : "muted"}>
                    <td>
                      <b>{a.label}</b>
                      <div className="small muted mono">{a.name}</div>
                    </td>
                    <td className="small" style={{ maxWidth: 360 }}>
                      {a.description}
                      {a.tools.length ? (
                        <TechnicalDetails title={`${a.n_tools} tools`}>
                          <span className="mono small">{a.tools.join(", ")}</span>
                        </TechnicalDetails>
                      ) : null}
                    </td>
                    <td className="num">{a.n_tools}</td>
                    <td className="num">{num.format(a.invocations)}</td>
                    <td className="num">{num.format(a.llm_calls)}</td>
                    <td className="num">{num.format(a.tool_calls)}</td>
                    <td className="num">
                      {fmtTokens(a.prompt_tokens)} / {fmtTokens(a.completion_tokens)}
                    </td>
                    <td className="num">
                      {fmtCost(a.cost_usd, a.unpriced_calls)}
                      {a.share_of_cost > 0 ? <div className="small muted">{(a.share_of_cost * 100).toFixed(0)}%</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {chart.length ? (
            <div className="grid grid-2" style={{ marginTop: 14 }}>
              <div>
                <div className="small muted" style={{ marginBottom: 4 }}>
                  Cost per agent (USD)
                </div>
                <ResponsiveContainer width="100%" height={Math.max(120, chart.length * 30 + 20)}>
                  <BarChart data={chart} layout="vertical" margin={{ top: 4, right: 48, left: 8, bottom: 0 }} barCategoryGap={6}>
                    <CartesianGrid horizontal={false} stroke="var(--border)" />
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(v) => usd.format(Number(v ?? 0))} />
                    <Bar dataKey="cost" fill="var(--primary)" radius={[0, 4, 4, 0]} barSize={18} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div>
                <div className="small muted" style={{ marginBottom: 4 }}>
                  Most used tools
                </div>
                {report.tools.length ? (
                  <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                    {report.tools.slice(0, 8).map((x) => (
                      <li key={x.name}>
                        <span className="mono">{x.name}</span> · {num.format(x.calls)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="empty">No tool calls yet.</div>
                )}
              </div>
            </div>
          ) : null}
          <div className="small muted" style={{ marginTop: 10 }}>
            Counting since {report.since ? report.since.replace("T", " ").slice(0, 16) : "the start"}. Costs are estimates from token counts; thinking tokens are billed as output.{" "}
            <button className="btn sm link" onClick={() => setPage("settings")}>
              Set prices in Settings
            </button>
          </div>
        </>
      )}
    </div>
  );
}
