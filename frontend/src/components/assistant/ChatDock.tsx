import { useAssistant } from "../../assistant/AssistantContext";
import { useApp } from "../../context";
import { ChatPanel } from "./ChatPanel";
import { IconChat, IconClose, IconExpand, IconPlus } from "./ChatIcons";
import { fmtCost, fmtTokens } from "./UsagePanel";

export function ChatDock() {
  const { page, setPage } = useApp();
  const { dockOpen, setDockOpen, unread, status, sessions, currentSessionId, sessionUsage, messages, newSession } = useAssistant();
  if (page === "assistant") return null;
  const title = sessions.find((s) => s.session_id === currentSessionId)?.title ?? "Assistant";
  return (
    <>
      {dockOpen ? (
        <div className="chat-panel" role="dialog" aria-label="Assistant">
          <div className="chat-head">
            <span className="chat-head-mark" aria-hidden="true">
              <IconChat size={18} />
            </span>
            <div className="chat-head-text">
              <b>Assistant</b>
              <div className="small muted">
                {status?.configured ? `${status.model} · ${status.agent_mode === "team" ? "team of 6 agents" : "single agent"}` : "not connected"}
                {sessionUsage?.llm_calls ? ` · ${fmtTokens(sessionUsage.total_tokens)} tokens · ${fmtCost(sessionUsage.cost_usd, sessionUsage.unpriced_calls)}` : currentSessionId ? ` · ${title}` : ""}
              </div>
            </div>
            <div className="chat-head-actions">
              {messages.length ? (
                <button className="icon-btn ghost" onClick={newSession} title="New conversation" aria-label="New conversation">
                  <IconPlus />
                </button>
              ) : null}
              <button className="icon-btn ghost" onClick={() => { setDockOpen(false); setPage("assistant"); }} title="Open the full page" aria-label="Open the full page">
                <IconExpand />
              </button>
              <button className="icon-btn ghost" onClick={() => setDockOpen(false)} title="Close" aria-label="Close the assistant">
                <IconClose size={16} />
              </button>
            </div>
          </div>
          <ChatPanel />
        </div>
      ) : null}
      <button className={`chat-fab ${dockOpen ? "open" : ""}`} onClick={() => setDockOpen(!dockOpen)} aria-label={dockOpen ? "Close the assistant" : "Open the assistant"} aria-expanded={dockOpen}>
        {dockOpen ? <IconClose size={22} /> : <IconChat size={26} />}
        {!dockOpen && unread ? <span className="badge">{unread}</span> : null}
      </button>
    </>
  );
}
