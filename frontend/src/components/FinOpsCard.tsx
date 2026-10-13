import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { useAssistant } from "../assistant/AssistantContext";
import { errorMessage, useApp } from "../context";
import type { FinOpsReport, FinOpsSpend } from "../types";
import { num } from "../utils";
import { fmtCost, fmtTokens, usd } from "./assistant/UsagePanel";
import { Help, Spinner } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";

const CHAT_COLOR = "#2a78d6";
const EMBED_COLOR = "#1baf7a";

const BUDGET_CHIP: Record<FinOpsReport["budget"]["status"], { cls: string; label: string }> = {
  none: { cls: "neutral", label: "No budget set" },
  ok: { cls: "status-done", label: "✓ On track" },
  at_risk: { cls: "status-running", label: "! Projected over budget" },
  over: { cls: "status-failed", label: "✕ Over budget" },
};

function SpendStat({ label, spend, sub }: { label: string; spend: FinOpsSpend; sub?: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{fmtCost(spend.cost_usd, spend.unpriced_calls)}</div>
      <div className="sub">{sub ?? `${fmtTokens(spend.tokens)} tokens · ${num.format(spend.calls)} calls`}</div>
    </div>
  );
}

/** AI spend on the gateway: by period, against a monthly budget, chat vs document embeddings, per agent. */
export function FinOpsCard() {
  const { toast } = useApp();
  const { streaming } = useAssistant();
  const [report, setReport] = useState<FinOpsReport | null>(null);
  const [budget, setBudget] = useState("");
  const [busy, setBusy] = useState<"load" | "save" | null>(null);

  const load = useCallback(async () => {
    setBusy("load");
    try {
      const r = await api.settings.finops();
      setReport(r);
      setBudget(r.budget.monthly_usd ? String(r.budget.monthly_usd) : "");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  }, [toast]);

  useEffect(() => {
    if (!streaming) void load();
  }, [load, streaming]);

  const saveBudget = async () => {
    const amount = Number(budget || 0);
    if (!Number.isFinite(amount) || amount < 0) return toast("Enter a budget of 0 or more", "error");
    setBusy("save");
    try {
      const r = await api.settings.setBudget(amount);
      setReport(r);
      toast(amount ? `Monthly budget set to ${usd.format(amount)}` : "Monthly budget removed", "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  const b = report?.budget;
  const chip = BUDGET_CHIP[b?.status ?? "none"];
  const chat = report?.chat;
  const emb = report?.embeddings;
  const daily = (report?.daily ?? []).map((d) => ({ ...d, label: d.day.slice(5) }));
  const hasDaily = daily.some((d) => d.chat_usd > 0 || d.embeddings_usd > 0);
  const totalCost = (chat?.cost_usd ?? 0) + (emb?.cost_usd ?? 0);
  const unpriced = (chat?.unpriced_calls ?? 0) + (emb?.unpriced_calls ?? 0);

  return (
    <div className="card">
      <div className="card-title">
        <h3>
          FinOps <Help text="Estimated AI spend on the gateway: chat (every agent's model calls) and document embeddings. Cost = tokens × the prices shown below; calls with no known price are counted but not costed (shown as +)." />
        </h3>
        <div className="row" style={{ gap: 6 }}>
          <span className={`chip ${chip.cls}`}>{chip.label}</span>
          <button className="btn sm" onClick={() => void load()} disabled={busy !== null}>
            {busy === "load" ? <Spinner /> : null} Refresh
          </button>
        </div>
      </div>
      {!report ? (
        <div className="empty">{busy ? "Loading…" : "No usage recorded yet."}</div>
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          <div className="grid grid-4">
            <div className="stat">
              <div className="label">{b?.month ?? "This month"}</div>
              <div className="value">{fmtCost(report.periods.month_to_date.cost_usd, report.periods.month_to_date.unpriced_calls)}</div>
              {b && b.monthly_usd > 0 ? (
                <>
                  <div className="progress" style={{ marginTop: 6 }} role="progressbar" aria-valuenow={Math.round((b.used_pct ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Budget used">
                    <div style={{ width: `${Math.min(100, (b.used_pct ?? 0) * 100)}%`, background: b.status === "over" ? "var(--critical)" : b.status === "at_risk" ? "var(--warning)" : undefined }} />
                  </div>
                  <div className="sub">
                    {((b.used_pct ?? 0) * 100).toFixed(0)}% of {usd.format(b.monthly_usd)}
                    {b.projected_usd != null ? ` · on pace for ${fmtCost(b.projected_usd)}` : ""}
                  </div>
                </>
              ) : (
                <div className="sub">{b?.projected_usd != null ? `on pace for ${fmtCost(b.projected_usd)}` : "month to date"}</div>
              )}
            </div>
            <SpendStat label="Today" spend={report.periods.today} />
            <SpendStat label="Last 7 days" spend={report.periods.last_7_days} />
            <SpendStat label="All time" spend={report.periods.all_time} sub={report.since ? `since ${report.since.slice(0, 10)}` : undefined} />
          </div>

          <div className="grid grid-2">
            <div>
              <div className="small muted" style={{ marginBottom: 6 }}>
                Chat {totalCost > 0 ? `· ${((chat!.cost_usd / totalCost) * 100).toFixed(0)}% of spend` : ""}
              </div>
              <dl className="kv">
                <dt>Conversations</dt>
                <dd>{num.format(chat!.conversations)}</dd>
                <dt>Questions answered</dt>
                <dd>{num.format(chat!.questions)}</dd>
                <dt>Cost per question</dt>
                <dd>{fmtCost(chat!.avg_cost_per_question, chat!.unpriced_calls)}</dd>
                <dt>Tokens per question</dt>
                <dd>{fmtTokens(chat!.avg_tokens_per_question)}</dd>
                <dt>Model calls per question</dt>
                <dd>{chat!.avg_calls_per_question.toFixed(1)}</dd>
                <dt>Tool calls</dt>
                <dd>{num.format(chat!.tool_calls)}</dd>
              </dl>
              <div className="small muted" style={{ margin: "12px 0 6px" }}>
                Document embeddings {totalCost > 0 ? `· ${((emb!.cost_usd / totalCost) * 100).toFixed(0)}% of spend` : ""}
              </div>
              {emb && emb.calls ? (
                <dl className="kv">
                  <dt>Model</dt>
                  <dd className="mono">{emb.model || "none (keyword search)"}</dd>
                  <dt>Requests</dt>
                  <dd>
                    {num.format(emb.calls)} ({num.format(emb.inputs)} passages)
                  </dd>
                  <dt>Tokens</dt>
                  <dd>
                    {fmtTokens(emb.tokens)}
                    {emb.estimated_tokens ? <span className="muted"> (partly estimated)</span> : null}
                  </dd>
                  <dt>Cost</dt>
                  <dd>{fmtCost(emb.cost_usd, emb.unpriced_calls)}</dd>
                </dl>
              ) : (
                <div className="small muted">{emb?.model ? `No embedding requests yet (${emb.model}).` : "Off: no embedding model set, documents use keyword search."}</div>
              )}
            </div>
            <div>
              <div className="small muted" style={{ marginBottom: 6 }}>
                Spend by agent
              </div>
              {report.agents.length ? (
                <div className="table-wrap" style={{ maxHeight: 260 }}>
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Agent</th>
                        <th className="num">Questions</th>
                        <th className="num">Tokens</th>
                        <th className="num">Cost</th>
                        <th className="num">Share</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.agents.map((a) => (
                        <tr key={a.name}>
                          <td>{a.label}</td>
                          <td className="num">{num.format(a.invocations)}</td>
                          <td className="num">{fmtTokens(a.tokens)}</td>
                          <td className="num">{fmtCost(a.cost_usd, a.unpriced_calls)}</td>
                          <td className="num">{chat!.cost_usd ? `${((a.cost_usd / chat!.cost_usd) * 100).toFixed(0)}%` : "–"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty">No chat yet.</div>
              )}
            </div>
          </div>

          <div>
            <div className="small muted" style={{ marginBottom: 4 }}>
              Daily spend, last 30 days (USD)
            </div>
            {hasDaily ? (
              <>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={daily} margin={{ top: 4, right: 8, left: 0, bottom: 0 }} barCategoryGap={2}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--text-3)" }} interval={4} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
                    <YAxis tick={{ fontSize: 11, fill: "var(--text-3)" }} width={56} tickFormatter={(v) => fmtCost(Number(v))} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(v, name) => [usd.format(Number(v ?? 0)), name]} labelFormatter={(l) => `Day ${l}`} cursor={{ fill: "var(--surface-2)" }} />
                    <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12, color: "var(--text-2)" }} />
                    <Bar dataKey="chat_usd" name="Chat" stackId="spend" fill={CHAT_COLOR} stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
                    <Bar dataKey="embeddings_usd" name="Embeddings" stackId="spend" fill={EMBED_COLOR} stroke="var(--surface)" strokeWidth={1} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
                <TechnicalDetails title="Daily figures">
                  <div className="table-wrap" style={{ maxHeight: 220 }}>
                    <table className="data">
                      <thead>
                        <tr>
                          <th>Day</th>
                          <th className="num">Chat</th>
                          <th className="num">Embeddings</th>
                          <th className="num">Tokens</th>
                        </tr>
                      </thead>
                      <tbody>
                        {daily
                          .filter((d) => d.tokens > 0)
                          .reverse()
                          .map((d) => (
                            <tr key={d.day}>
                              <td>{d.day}</td>
                              <td className="num">{fmtCost(d.chat_usd)}</td>
                              <td className="num">{fmtCost(d.embeddings_usd)}</td>
                              <td className="num">{fmtTokens(d.tokens)}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </TechnicalDetails>
              </>
            ) : (
              <div className="empty">No priced usage in the last 30 days.</div>
            )}
          </div>

          <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
            <label className="field" style={{ maxWidth: 220 }}>
              <span>
                Monthly budget (USD) <Help text="A soft limit per calendar month: the card warns when this month's spend is projected to pass it, or has. Nothing is blocked. Blank or 0 = no budget." />
              </span>
              <input type="number" min={0} step={1} value={budget} placeholder="no budget" onChange={(e) => setBudget(e.target.value)} />
            </label>
            <button className="btn" onClick={saveBudget} disabled={busy !== null || Number(budget || 0) === (b?.monthly_usd ?? 0)}>
              {busy === "save" ? <Spinner /> : null} Save budget
            </button>
            <span className="small muted" style={{ flex: 1, minWidth: 240 }}>
              Prices:{" "}
              {report.pricing.chat
                ? report.pricing.chat.known
                  ? `chat ${usd.format(report.pricing.chat.input_per_m)} in / ${usd.format(report.pricing.chat.output_per_m)} out per 1M (${report.pricing.chat.source})`
                  : "chat model has no known price: set one above"
                : "no chat model"}
              {report.pricing.embeddings ? (report.pricing.embeddings.known ? ` · embeddings ${usd.format(report.pricing.embeddings.input_per_m)} per 1M (${report.pricing.embeddings.source})` : " · embedding model has no known price") : ""}
              {unpriced ? ` · ${num.format(unpriced)} unpriced calls not in the totals` : ""}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
