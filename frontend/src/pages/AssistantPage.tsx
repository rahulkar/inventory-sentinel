import { useAssistant } from "../assistant/AssistantContext";
import { ChatPanel } from "../components/assistant/ChatPanel";
import { UsagePanel, fmtCost, fmtTokens } from "../components/assistant/UsagePanel";
import { ConversationsArt, EmptyState } from "../components/Illustrations";
import { useApp } from "../context";
import { fmtDate } from "../utils";

export function AssistantPage() {
  const { sessions, currentSessionId, openSession, deleteSession, newSession, status, sessionUsage } = useAssistant();
  const { setPage } = useApp();
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Assistant</h1>
          <p>
            A team of agents that knows what is loaded, reads your data, models, alerts and team feedback, explains why something was flagged, plans investigator time, and proposes jobs you confirm before they run.
            {status?.configured ? ` Connected to ${status.model} via ${status.base_host}.` : " Not connected yet."}
            {sessionUsage?.llm_calls ? ` This conversation so far: ${sessionUsage.llm_calls} model calls, ${fmtTokens(sessionUsage.total_tokens)} tokens, ${fmtCost(sessionUsage.cost_usd, sessionUsage.unpriced_calls)}.` : ""}
          </p>
        </div>
        <div className="row">
          <button className="btn" onClick={() => setPage("settings")}>
            ⚙ Settings
          </button>
          <button className="btn primary" onClick={newSession}>
            New conversation
          </button>
        </div>
      </div>
      <div className="grid grid-side" style={{ gridTemplateColumns: "300px minmax(0, 1fr)" }}>
        <div className="card">
          <div className="card-title">
            <h3>Conversations</h3>
          </div>
          {sessions.length ? (
            <div className="list">
              {sessions.map((s) => (
                <div key={s.session_id} className={`list-item ${s.session_id === currentSessionId ? "selected" : ""}`} onClick={() => void openSession(s.session_id)}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="title" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.title}
                    </div>
                    <div className="meta">{s.updated_at ? fmtDate(s.updated_at) : s.created_at ? fmtDate(s.created_at) : ""}</div>
                  </div>
                  <button
                    className="btn sm danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm("Delete this conversation?")) void deleteSession(s.session_id);
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState art={<ConversationsArt />}>
              <b>No conversations yet.</b>
              <div className="muted small">Ask something in the chat and it will be saved here.</div>
            </EmptyState>
          )}
        </div>
        <div className="card chat-card">
          <ChatPanel full />
        </div>
      </div>
      <UsagePanel sessionId={currentSessionId} />
    </div>
  );
}
