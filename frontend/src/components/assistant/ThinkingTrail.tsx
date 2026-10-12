import { useEffect, useState } from "react";
import type { ChatMessage, ToolActivity } from "../../types";
import { Spinner } from "../Layout";

export const AGENT_LABELS: Record<string, string> = {
  sentinel_assistant: "Front door",
  data_analyst: "Data analyst",
  model_analyst: "Model analyst",
  alert_investigator: "Alert investigator",
  lp_planner: "Loss-prevention planner",
  explainer: "Explainer",
};

const AGENT_INITIALS: Record<string, string> = {
  sentinel_assistant: "FD",
  data_analyst: "DA",
  model_analyst: "MA",
  alert_investigator: "AI",
  lp_planner: "LP",
  explainer: "EX",
};

export function agentLabel(name?: string | null): string {
  if (!name) return "Assistant";
  return AGENT_LABELS[name] ?? name.replace(/_/g, " ");
}

function Avatar({ name }: { name?: string | null }) {
  const key = name ?? "sentinel_assistant";
  return (
    <span className={`agent-avatar a-${key}`} title={agentLabel(name)}>
      {AGENT_INITIALS[key] ?? key.slice(0, 2).toUpperCase()}
    </span>
  );
}

function fmtMs(ms: number): string {
  if (ms < 1000) return `${Math.max(1, Math.round(ms / 100)) / 10}s`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

interface Step {
  kind: "start" | "transfer" | "tool" | "answer";
  agent: string | null;
  title: string;
  detail?: string | null;
  status: "running" | "done" | "failed";
  ms?: number;
}

function buildSteps(m: ChatMessage, now: number): Step[] {
  const steps: Step[] = [];
  const firstAgent = m.tools[0]?.author ?? m.author ?? "sentinel_assistant";
  steps.push({ kind: "start", agent: firstAgent, title: `${agentLabel(firstAgent)} is reading the question`, status: "done" });
  let current: string | null = firstAgent;
  for (const t of m.tools as ToolActivity[]) {
    if (t.name === "transfer") {
      current = t.to ?? current;
      steps.push({ kind: "transfer", agent: t.author ?? null, title: `Handing over to ${agentLabel(t.to)}`, detail: t.to ? describeHandover(t.to) : null, status: "done" });
      continue;
    }
    const running = t.ok === null && m.pending;
    steps.push({
      kind: "tool",
      agent: t.author ?? current,
      title: t.label,
      detail: t.summary,
      status: running ? "running" : t.ok === false ? "failed" : "done",
      ms: t.at ? (t.doneAt ?? (running ? now : t.at)) - t.at : undefined,
    });
  }
  const answerAgent = m.author ?? current ?? firstAgent;
  if (m.pending) {
    const toolRunning = steps.some((s) => s.status === "running");
    if (!toolRunning) steps.push({ kind: "answer", agent: answerAgent, title: m.text ? `${agentLabel(answerAgent)} is writing the answer` : `${agentLabel(answerAgent)} is thinking`, status: "running" });
  } else if (!m.error) {
    steps.push({ kind: "answer", agent: answerAgent, title: `${agentLabel(answerAgent)} answered`, status: "done" });
  }
  return steps;
}

function describeHandover(to: string): string {
  switch (to) {
    case "data_analyst":
      return "datasets, columns, loss-prevention flags";
    case "model_analyst":
      return "methods, metrics, drivers, training";
    case "alert_investigator":
      return "alerts, reasons, drill-downs, hotspots";
    case "lp_planner":
      return "investigator hours, ROI, work lists";
    case "explainer":
      return "how it works, glossary";
    default:
      return "";
  }
}

/** Gemini-style "thinking" panel: who read the question, hand-overs, tool calls and the answer, with timings. */
export function ThinkingTrail({ m }: { m: ChatMessage }) {
  const [open, setOpen] = useState<boolean | null>(null); // null = follow the default (open while pending)
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!m.pending) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [m.pending]);

  const hasActivity = m.tools.length > 0;
  if (!hasActivity && !m.pending) return null;
  const steps = buildSteps(m, now);
  const expanded = open ?? m.pending;
  const total = m.startedAt ? (m.endedAt ?? now) - m.startedAt : null;
  const agents = Array.from(new Set(steps.map((s) => s.agent).filter(Boolean))) as string[];
  const toolCount = m.tools.filter((t) => t.name !== "transfer").length;
  const handovers = m.tools.filter((t) => t.name === "transfer").length;
  const summary = m.pending
    ? steps[steps.length - 1]?.title ?? "Thinking"
    : `Thought for ${total ? fmtMs(total) : "a moment"} · ${agents.map(agentLabel).join(" → ")}${toolCount ? ` · ${toolCount} tool${toolCount === 1 ? "" : "s"}` : ""}${handovers ? ` · ${handovers} hand-over${handovers === 1 ? "" : "s"}` : ""}`;

  return (
    <div className={`trail ${m.pending ? "live" : ""}`}>
      <button className="trail-head" onClick={() => setOpen(!expanded)} aria-expanded={expanded}>
        <span className="trail-glyph">{m.pending ? <Spinner /> : "✦"}</span>
        <span className="trail-summary">{summary}</span>
        <span className="trail-chevron">{expanded ? "▾" : "▸"}</span>
      </button>
      {expanded ? (
        <ol className="trail-steps">
          {steps.map((s, i) => (
            <li key={i} className={`trail-step ${s.kind} ${s.status}`}>
              <span className="trail-line" aria-hidden="true" />
              <Avatar name={s.agent} />
              <span className="trail-body">
                <span className="trail-title">
                  {s.kind === "transfer" ? <span className="trail-arrow">→ </span> : null}
                  {s.title}
                  {s.status === "running" ? <span className="trail-dots" aria-hidden="true" /> : null}
                </span>
                {s.detail ? <span className="trail-detail">{s.detail}</span> : null}
              </span>
              <span className="trail-status">{s.status === "running" ? (s.ms !== undefined ? fmtMs(s.ms) : "") : s.status === "failed" ? "✕" : s.ms !== undefined && s.kind === "tool" ? `✓ ${fmtMs(s.ms)}` : "✓"}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
