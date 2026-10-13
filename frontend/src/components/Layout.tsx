import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useAssistant } from "../assistant/AssistantContext";
import { useApp, type Page } from "../context";
import { ChatDock } from "./assistant/ChatDock";
import { AlertDrawer } from "./AlertDrawer";
import { JobProgress } from "./JobProgress";
import { isTerminal, OUTCOME_LABEL, SEVERITY_LABEL, TYPE_HELP, TYPE_LABEL } from "../utils";

const BUSINESS: { key: Page; label: string; step: number }[] = [
  { key: "data", label: "Data", step: 1 },
  { key: "train", label: "Train", step: 2 },
  { key: "act", label: "Act", step: 3 },
];
const EXEC: { key: Page; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "alerts", label: "Alerts" },
  { key: "plan", label: "Plan" },
];
const OPERATIONS: { key: Page; label: string }[] = [{ key: "schedules", label: "Schedules" }];
const ANALYST: { key: Page; label: string }[] = [
  { key: "models", label: "Models" },
  { key: "experiments", label: "Experiments" },
];

export function Layout({ children }: { children: ReactNode }) {
  const { page, setPage, mode, setMode, activeModel, toasts, backendOk, activeJobs, jobs, cancelJob } = useApp();
  const exec = mode === "exec";
  const { status: ai } = useAssistant();
  const [jobsOpen, setJobsOpen] = useState(false);
  const recent = Object.values(jobs)
    .filter((j) => isTerminal(j.status))
    .sort((a, b) => (b.finished_at ?? "").localeCompare(a.finished_at ?? ""))
    .slice(0, 3);
  const lead = activeJobs[0];
  const headerRef = useRef<HTMLElement>(null);
  const navRef = useRef<HTMLElement>(null);

  // the nav's width depends on the mode, the AI model name, the model label and the jobs pill, so breakpoints
  // alone cannot tell when it fits: measure it on one row and give it its own row when it would overflow
  useLayoutEffect(() => {
    const fit = () => {
      const header = headerRef.current;
      const nav = navRef.current;
      if (!header || !nav) return;
      header.classList.remove("wrap-nav");
      header.classList.toggle("wrap-nav", nav.scrollWidth > nav.clientWidth + 1);
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  });

  return (
    <>
      <header className="topbar" ref={headerRef}>
        <div className="topbar-inner">
          <button className="brand" onClick={() => setPage("overview")} title="Home">
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18">
                <path d="M12 2 3 5.5v6.2c0 5.1 3.8 9.4 9 10.3 5.2-.9 9-5.2 9-10.3V5.5L12 2z" fill="currentColor" />
                <path d="M8 11.5h8v5H8z M9.5 9h5v2.5h-5z" fill="#fff" />
              </svg>
            </span>
            <span className="brand-word">Inventory Sentinel</span>
          </button>
          {exec ? (
          <nav className="nav" ref={navRef}>
            {EXEC.map((p) => (
              <button key={p.key} className={page === p.key ? "active" : ""} onClick={() => setPage(p.key)}>
                {p.label}
              </button>
            ))}
            <button className={`story-link exec-story ${page === "story" ? "active" : ""}`} onClick={() => setPage("story")}>
              ▶ Story
            </button>
          </nav>
          ) : (
          <nav className="nav" ref={navRef}>
            <button className={`story-link ${page === "story" ? "active" : ""}`} onClick={() => setPage("story")}>
              How it works
            </button>
            <span className="nav-divider" />
            <div className="nav-group" role="group" aria-label="Business">
              <span className="nav-caption">Business</span>
              {BUSINESS.map((p) => (
                <button key={p.key} className={page === p.key ? "active" : ""} onClick={() => setPage(p.key)}>
                  <span className="step">{p.step}</span>
                  {p.label}
                </button>
              ))}
            </div>
            <span className="nav-divider" />
            <div className="nav-group" role="group" aria-label="Operations">
              <span className="nav-caption">Operations</span>
              {OPERATIONS.map((p) => (
                <button key={p.key} className={page === p.key ? "active" : ""} onClick={() => setPage(p.key)}>
                  {p.label}
                </button>
              ))}
            </div>
            <span className="nav-divider" />
            <div className="nav-group" role="group" aria-label="Analyst">
              <span className="nav-caption">Analyst</span>
              {ANALYST.map((p) => (
                <button key={p.key} className={page === p.key ? "active" : ""} onClick={() => setPage(p.key)}>
                  {p.label}
                </button>
              ))}
            </div>
            <span className="nav-divider" />
            <button className={page === "assistant" ? "active" : ""} onClick={() => setPage("assistant")}>
              Assistant
            </button>
          </nav>
          )}
          <div className="topbar-right">
            <div className="mode-switch" role="group" aria-label="View">
              <button className={exec ? "on" : ""} aria-pressed={exec} onClick={() => setMode("exec")} title="Lean view for leadership: the answer, the alerts and the plan">
                Executive
              </button>
              <button className={!exec ? "on" : ""} aria-pressed={!exec} onClick={() => setMode("analyst")} title="Every page: data, training, models, experiments and all Act tabs">
                Analyst
              </button>
            </div>
            {exec ? null : (
            <button className={`ai-chip ${ai?.configured && ai.available ? "on" : ""} ${page === "settings" ? "active" : ""}`} onClick={() => setPage("settings")} title={`AI gateway settings${ai?.configured && ai.available ? ` (model: ${ai.model})` : ""}`}>
              <span className={`dot ${ai?.configured && ai.available ? "" : "off"}`} />
              <span className="hide-compact clip">{ai?.configured && ai.available ? `AI: ${ai.model}` : "AI: not configured"}</span>
              <span className="gear">⚙</span>
            </button>
            )}
            {activeJobs.length || (!exec && recent.length) ? (
              <button className={`jobs-pill ${lead ? "busy" : ""}`} onClick={() => setJobsOpen((o) => !o)} title={lead ? lead.title : "Recent jobs"} aria-expanded={jobsOpen}>
                {lead ? (
                  <>
                    <span className="spinner" />
                    {lead.percent.toFixed(0)}%{activeJobs.length > 1 ? ` (+${activeJobs.length - 1})` : ""}
                  </>
                ) : (
                  "Recent jobs"
                )}
              </button>
            ) : null}
            {exec ? null : (
            <div className="active-model" title={activeModel ? `Using ${activeModel.label}` : undefined}>
              <span className={`dot ${backendOk ? "" : "off"}`} />
              {backendOk === false ? (
                <span>API offline</span>
              ) : activeModel ? (
                <span className="clip">
                  Using <b>{activeModel.label}</b>
                  {activeModel.metrics.average_precision !== null ? <span className="hide-compact"> · AP {activeModel.metrics.average_precision.toFixed(2)}</span> : null}
                </span>
              ) : (
                <span>No model in use yet</span>
              )}
            </div>
            )}
          </div>
        </div>
        {jobsOpen ? (
          <div className="jobs-popover" onMouseLeave={() => setJobsOpen(false)}>
            {activeJobs.length === 0 && recent.length === 0 ? <div className="muted small">No jobs yet.</div> : null}
            {activeJobs.map((j) => (
              <JobProgress key={j.job_id} job={j} compact onCancel={cancelJob} />
            ))}
            {recent.map((j) => (
              <JobProgress key={j.job_id} job={j} compact />
            ))}
          </div>
        ) : null}
      </header>
      <main className="page">{children}</main>
      <ChatDock />
      <AlertDrawer />
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.message}
          </div>
        ))}
      </div>
    </>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function StatCard({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub ? <div className="sub">{sub}</div> : null}
    </div>
  );
}

export function SeverityChip({ severity }: { severity: string }) {
  const icon = severity === "critical" ? "▲" : severity === "high" ? "◆" : "●";
  return (
    <span className={`chip sev-${severity}`}>
      <span aria-hidden="true">{icon}</span>
      {SEVERITY_LABEL[severity] ?? severity}
    </span>
  );
}

export function TypeChip({ type, confidence }: { type: string; confidence?: number }) {
  return (
    <span className={`chip type-chip t-${type}`} title={`${TYPE_HELP[type] ?? ""}${confidence !== undefined ? ` (rule confidence ${Math.round(confidence * 100)}%)` : ""}`}>
      <span className="type-dot" aria-hidden="true" />
      {TYPE_LABEL[type] ?? type}
    </span>
  );
}

export function OutcomeChip({ outcome }: { outcome: string }) {
  const icon = outcome === "false_alarm" ? "✕" : outcome === "open" ? "○" : "✓";
  return (
    <span className={`chip out-${outcome}`}>
      <span aria-hidden="true">{icon}</span>
      {OUTCOME_LABEL[outcome] ?? outcome}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip status-${status}`}>{status}</span>;
}

export function Help({ text }: { text: string }) {
  return (
    <span className="help" title={text} aria-label={text}>
      ?
    </span>
  );
}
