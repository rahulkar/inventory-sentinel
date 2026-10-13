import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ProposalCard } from "../ProposalCard";
import { fmtCost, fmtTokens } from "./UsagePanel";
import { ThinkingTrail, agentLabel } from "./ThinkingTrail";
import { useAssistant } from "../../assistant/AssistantContext";
import { useSpeechInput } from "../../assistant/useSpeechInput";
import { ChatEmptyArt, ConnectArt } from "../Illustrations";
import { useApp } from "../../context";
import type { ChatMessage, Proposal } from "../../types";
import { fmtDuration } from "../../utils";
import { JobProgress } from "../JobProgress";
import { Spinner } from "../Layout";
import { TechnicalDetails } from "../TechnicalDetails";

/** Minimal markdown: paragraphs, bullets, numbered lists, **bold**, `code`. */
function Markdown({ text }: { text: string }) {
  const blocks = text.replace(/\r/g, "").split(/\n{2,}/);
  const inline = (s: string): ReactNode[] => {
    const parts: ReactNode[] = [];
    const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((?:https?:\/\/|\/)[^)\s]+\))/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let k = 0;
    while ((m = re.exec(s))) {
      if (m.index > last) parts.push(s.slice(last, m.index));
      const tok = m[0];
      if (tok.startsWith("**")) parts.push(<b key={k++}>{tok.slice(2, -2)}</b>);
      else if (tok.startsWith("`")) parts.push(<code key={k++}>{tok.slice(1, -1)}</code>);
      else {
        const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)!;
        parts.push(
          <a key={k++} href={link[2]} target="_blank" rel="noreferrer">
            {link[1]}
          </a>,
        );
      }
      last = m.index + tok.length;
    }
    if (last < s.length) parts.push(s.slice(last));
    return parts;
  };
  return (
    <>
      {blocks.map((b, i) => {
        const lines = b.split("\n").filter((l) => l.trim().length);
        if (!lines.length) return null;
        if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-*•]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        if (lines.every((l) => /^\s*\d+[.)]\s+/.test(l))) {
          return (
            <ol key={i}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*\d+[.)]\s+/, ""))}</li>
              ))}
            </ol>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <span key={j}>
                {inline(l.replace(/^#+\s*/, ""))}
                {j < lines.length - 1 ? <br /> : null}
              </span>
            ))}
          </p>
        );
      })}
    </>
  );
}

function ChatProposal({ p }: { p: Proposal }) {
  const { confirm, cancel } = useAssistant();
  return <ProposalCard p={p} onConfirm={confirm} onCancel={cancel} />;
}

function Bubble({ m }: { m: ChatMessage }) {
  if (m.role === "system") {
    return (
      <div className="msg system">
        <span>{m.text.replace(/^\[[^\]]+\]\s*/, "")}</span>
      </div>
    );
  }
  return (
    <div className={`msg ${m.role}`}>
      {m.role === "assistant" ? <ThinkingTrail m={m} /> : null}
      {m.role === "assistant" && m.author && m.author !== "sentinel_assistant" && m.text ? <div className="author">{agentLabel(m.author)}</div> : null}
      {m.text ? <div className="bubble">{m.role === "assistant" ? <Markdown text={m.text} /> : m.text}</div> : null}
      {m.proposals.map((p) => (
        <ChatProposal key={p.proposal_id} p={p} />
      ))}
      {m.error ? <div className="alert error small" style={{ marginTop: 6 }}>{m.error}</div> : null}
      {m.role === "assistant" && m.usage && !m.pending ? (
        <div className="msg-usage" title="Model calls · tokens in / out · estimated cost">
          {m.usage.llm_calls} call{m.usage.llm_calls === 1 ? "" : "s"} · {fmtTokens(m.usage.prompt_tokens)} / {fmtTokens(m.usage.completion_tokens)} tokens · {fmtCost(m.usage.cost_usd, m.usage.unpriced ? 1 : 0)}
        </div>
      ) : null}
    </div>
  );
}

export function ChatPanel({ full = false }: { full?: boolean }) {
  const { status, messages, streaming, send, abort, quickPrompts, newSession } = useAssistant();
  const { setPage } = useApp();
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const speech = useSpeechInput((phrase) => setDraft((d) => (d.trim() ? `${d.trim()} ${phrase}` : phrase)));

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming]);

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (draft.trim() && !streaming) {
        void send(draft);
        setDraft("");
      }
    }
  };

  const notConfigured = status && (!status.configured || !status.available);
  return (
    <div className={`chat-panel-body ${full ? "full" : ""}`}>
      <div className="chat-messages" ref={listRef}>
        {notConfigured ? (
          <div className="chat-empty">
            <ConnectArt className="chat-empty-art" />
            <b>{status?.available === false ? "The assistant is unavailable on this machine." : "Connect an AI gateway to start chatting."}</b>
            <div className="muted small" style={{ margin: "6px 0 10px" }}>
              {status?.available === false ? status.reason : "Enter the lab's LiteLLM endpoint, secret key and model in Settings, test the connection, and come back."}
            </div>
            <button className="btn primary sm" onClick={() => setPage("settings")}>
              Open Settings →
            </button>
          </div>
        ) : messages.length === 0 ? (
          <div className="chat-empty">
            <ChatEmptyArt className="chat-empty-art" />
            <b>Ask me about alerts, stores, items, models or the investigation plan.</b>
            <div className="muted small" style={{ margin: "6px 0 10px" }}>
              I can read everything in the app, explain it in plain words, and propose jobs that you confirm before they run.
              {speech.supported ? " Press the microphone to talk instead of typing." : ""}
            </div>
          </div>
        ) : (
          messages.map((m) => <Bubble key={m.id} m={m} />)
        )}
      </div>
      {!notConfigured ? (
        <div className="quick-prompts">
          {quickPrompts.map((q) => (
            <button key={q} className="toggle-chip" disabled={streaming} onClick={() => void send(q)}>
              {q}
            </button>
          ))}
        </div>
      ) : null}
      {speech.error ? <div className="alert error small composer-note">{speech.error}</div> : null}
      {speech.listening ? (
        <div className="composer-note listening">
          <span className="mic-pulse" aria-hidden="true" /> Listening… {speech.interim ? <em>{speech.interim}</em> : <span className="muted">speak now; it stops after a pause</span>}
        </div>
      ) : null}
      <div className="composer">
        <textarea rows={2} placeholder={notConfigured ? "Configure the gateway in Settings first" : speech.listening ? "Listening…" : "Ask anything… (Enter to send, Shift+Enter for a new line)"} value={draft} disabled={!!notConfigured} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} />
        {speech.supported && !notConfigured ? (
          <button className={`btn mic ${speech.listening ? "on" : ""}`} onClick={speech.toggle} title={speech.listening ? "Stop listening" : "Speak your question (browser speech-to-text)"} aria-pressed={speech.listening} aria-label="Voice input">
            {speech.listening ? "■" : "🎤"}
          </button>
        ) : null}
        {streaming ? (
          <button className="btn" onClick={abort} title="Stop">
            Stop
          </button>
        ) : (
          <button className="btn primary" disabled={!draft.trim() || !!notConfigured} onClick={() => { void send(draft); setDraft(""); }}>
            Send
          </button>
        )}
        {messages.length ? (
          <button className="btn sm link" onClick={newSession} title="Start a new conversation">
            New
          </button>
        ) : null}
      </div>
    </div>
  );
}
