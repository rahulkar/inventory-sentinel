import { useAssistant } from "../../assistant/AssistantContext";
import { useApp } from "../../context";
import { ChatPanel } from "./ChatPanel";
import { fmtCost, fmtTokens } from "./UsagePanel";

export function ChatDock() {
  const { page, setPage } = useApp();
  const { dockOpen, setDockOpen, unread, status, sessions, currentSessionId, sessionUsage } = useAssistant();
  if (page === "assistant") return null;
  const title = sessions.find((s) => s.session_id === currentSessionId)?.title ?? "Assistant";
  return (
    <>
      {dockOpen ? (
        <div className="chat-panel" role="dialog" aria-label="Assistant">
          <div className="chat-head">
            <div style={{ minWidth: 0 }}>
              <b>Assistant</b>
              <div className="small muted" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {status?.configured ? `${status.model} · ${status.agent_mode === "team" ? "team of 6 agents" : "single agent"}` : "not connected"}
                {sessionUsage?.llm_calls ? ` · ${fmtTokens(sessionUsage.total_tokens)} tokens · ${fmtCost(sessionUsage.cost_usd, sessionUsage.unpriced_calls)}` : currentSessionId ? ` · ${title}` : ""}
              </div>
            </div>
            <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
              <button className="btn sm link" onClick={() => { setDockOpen(false); setPage("assistant"); }} title="Open the full page">
                Expand
              </button>
              <button className="btn sm link" onClick={() => setDockOpen(false)} title="Close">
                ✕
              </button>
            </div>
          </div>
          <ChatPanel />
        </div>
      ) : null}
      <button className={`chat-fab ${dockOpen ? "open" : ""}`} onClick={() => setDockOpen(!dockOpen)} aria-label="Toggle assistant">
        {dockOpen ? "✕" : "💬"}
        {!dockOpen && unread ? <span className="badge">{unread}</span> : null}
      </button>
    </>
  );
}
