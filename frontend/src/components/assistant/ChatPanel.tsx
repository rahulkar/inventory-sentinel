import { ArrowRight } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ProposalCard } from "../ProposalCard";
import { fmtCost, fmtTokens } from "./UsagePanel";
import { Avatar, ThinkingTrail, agentLabel } from "./ThinkingTrail";
import { IconCheck, IconCopy, IconMic, IconSend, IconStop } from "./ChatIcons";
import { useAssistant } from "../../assistant/AssistantContext";
import { useSpeechInput } from "../../assistant/useSpeechInput";
import { ChatEmptyArt, ConnectArt } from "../Illustrations";
import { useApp } from "../../context";
import type { ChatMessage, Proposal } from "../../types";

const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const cells = (row: string) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

/** Minimal markdown: paragraphs, headings, bullets, numbered lists, tables, **bold**, `code` and links. */
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
        if (lines.length >= 2 && lines.every((l) => TABLE_ROW.test(l)) && TABLE_RULE.test(lines[1])) {
          const head = cells(lines[0]);
          return (
            <div key={i} className="md-table">
              <table>
                <thead>
                  <tr>
                    {head.map((h, j) => (
                      <th key={j}>{inline(h)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {lines.slice(2).map((r, j) => (
                    <tr key={j}>
                      {cells(r).map((c, x) => (
                        <td key={x}>{inline(c)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
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
              <span key={j} className={/^#+\s/.test(l) ? "md-h" : undefined}>
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

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return;
    const id = setTimeout(() => setDone(false), 1500);
    return () => clearTimeout(id);
  }, [done]);
  return (
    <button
      className="msg-action"
      title="Copy the answer"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => setDone(true), () => undefined);
      }}
    >
      {done ? <IconCheck /> : <IconCopy />}
      {done ? "Copied" : "Copy"}
    </button>
  );
}

function Bubble({ m, onRetry }: { m: ChatMessage; onRetry?: () => void }) {
  if (m.role === "system") {
    return (
      <div className="msg system">
        <span>{m.text.replace(/^\[[^\]]+\]\s*/, "")}</span>
      </div>
    );
  }
  if (m.role === "user") {
    return (
      <div className="msg user">
        <div className="bubble">{m.text}</div>
      </div>
    );
  }
  const who = m.author && m.author !== "sentinel_assistant" ? agentLabel(m.author) : "Sentinel assistant";
  return (
    <div className="msg assistant">
      <div className="msg-head">
        <Avatar name={m.author} />
        <span>{who}</span>
      </div>
      <ThinkingTrail m={m} />
      {m.text ? (
        <div className="bubble">
          <Markdown text={m.text} />
        </div>
      ) : null}
      {m.proposals.map((p) => (
        <ChatProposal key={p.proposal_id} p={p} />
      ))}
      {m.error ? (
        <div className="alert error small msg-error">
          <span>{m.error}</span>
          {onRetry ? (
            <button className="btn sm" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      ) : null}
      {!m.pending && (m.text || m.usage) ? (
        <div className="msg-foot">
          {m.text ? <CopyButton text={m.text} /> : null}
          {m.usage ? (
            <span className="msg-usage" title="Model calls · tokens in / out · estimated cost">
              {m.usage.llm_calls} call{m.usage.llm_calls === 1 ? "" : "s"} · {fmtTokens(m.usage.prompt_tokens)} / {fmtTokens(m.usage.completion_tokens)} tokens · {fmtCost(m.usage.cost_usd, m.usage.unpriced ? 1 : 0)}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function ChatPanel({ full = false }: { full?: boolean }) {
  const { status, messages, streaming, send, abort, quickPrompts } = useAssistant();
  const { setPage } = useApp();
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const speech = useSpeechInput((phrase) => setDraft((d) => (d.trim() ? `${d.trim()} ${phrase}` : phrase)));

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming]);

  // the box grows with what is typed, up to about six lines, then scrolls
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
  }, [draft]);

  const submit = (text: string) => {
    if (!text.trim() || streaming) return;
    void send(text);
    setDraft("");
    inputRef.current?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit(draft);
    }
  };

  const notConfigured = status && (!status.configured || !status.available);
  return (
    <div className={`chat-panel-body ${full ? "full" : ""}`}>
      <div className="chat-messages" ref={listRef} aria-live="polite">
        {notConfigured ? (
          <div className="chat-empty">
            <ConnectArt className="chat-empty-art" />
            <b>{status?.available === false ? "The assistant is unavailable on this machine." : "Connect an AI gateway to start chatting."}</b>
            <div className="muted small">{status?.available === false ? status.reason : "Enter the lab's LiteLLM endpoint, secret key and model in Settings, test the connection, and come back."}</div>
            <button className="btn primary sm" onClick={() => setPage("settings")}>
              Open Settings <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        ) : messages.length === 0 ? (
          <div className="chat-empty">
            <ChatEmptyArt className="chat-empty-art" />
            <b>Ask me about alerts, stores, items, models or the investigation plan.</b>
            <div className="muted small">
              I can read everything in the app, explain it in plain words, and propose jobs that you confirm before they run.
              {speech.supported ? " Press the microphone to talk instead of typing." : ""}
            </div>
          </div>
        ) : (
          messages.map((m, i) => {
            // a failed answer can be asked again: resend the question just before it
            const q = m.error && !m.pending && !streaming ? messages.slice(0, i).reverse().find((x) => x.role === "user")?.text : undefined;
            return <Bubble key={m.id} m={m} onRetry={q ? () => submit(q) : undefined} />;
          })
        )}
      </div>
      {!notConfigured && !streaming ? (
        <div className="quick-prompts" aria-label="Suggested questions">
          {quickPrompts.map((q) => (
            <button key={q} className="prompt-chip" onClick={() => submit(q)}>
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
        <div className={`composer-box ${notConfigured ? "disabled" : ""}`}>
          <textarea
            ref={inputRef}
            rows={1}
            aria-label="Message the assistant"
            placeholder={notConfigured ? "Configure the gateway in Settings first" : speech.listening ? "Listening…" : "Ask anything…"}
            value={draft}
            disabled={!!notConfigured}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKey}
          />
          {speech.supported && !notConfigured ? (
            <button className={`icon-btn mic ${speech.listening ? "on" : ""}`} onClick={speech.toggle} title={speech.listening ? "Stop listening" : "Speak your question (browser speech-to-text)"} aria-pressed={speech.listening} aria-label="Voice input">
              {speech.listening ? <IconStop /> : <IconMic />}
            </button>
          ) : null}
          {streaming ? (
            <button className="icon-btn send stop" onClick={abort} title="Stop the answer" aria-label="Stop">
              <IconStop />
            </button>
          ) : (
            <button className="icon-btn send" disabled={!draft.trim() || !!notConfigured} onClick={() => submit(draft)} title="Send (Enter)" aria-label="Send">
              <IconSend />
            </button>
          )}
        </div>
        <div className="composer-hint">Enter to send · Shift+Enter for a new line · answers can be wrong, check the figures it cites</div>
      </div>
    </div>
  );
}
