import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, streamChat } from "../api";
import { errorMessage, useApp } from "../context";
import type { AssistantStatus, ChatEvent, ChatMessage, Proposal, SessionSummary, UiState, SessionUsage } from "../types";
import { isTerminal } from "../utils";

interface AssistantState {
  status: AssistantStatus | null;
  refreshStatus: () => Promise<void>;
  sessions: SessionSummary[];
  refreshSessions: () => Promise<void>;
  currentSessionId: string | null;
  messages: ChatMessage[];
  streaming: boolean;
  dockOpen: boolean;
  setDockOpen: (open: boolean) => void;
  unread: number;
  send: (text: string, opts?: { system?: boolean }) => Promise<void>;
  abort: () => void;
  confirm: (proposalId: string) => Promise<void>;
  cancel: (proposalId: string) => Promise<void>;
  newSession: () => void;
  openSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  quickPrompts: string[];
  sessionUsage: SessionUsage | null;
}

const Ctx = createContext<AssistantState | null>(null);
let seq = 0;
const mid = () => `m${Date.now()}_${++seq}`;

const QUICK: Record<string, string[]> = {
  overview: ["What do I have loaded right now?", "What are the top critical alerts?", "What should I do next?"],
  story: ["Explain how the detectors learn what normal looks like", "Why does ranking alerts beat working down by £ at risk?", "Which other business questions could this engine answer?"],
  data: ["Describe the selected dataset", "What does sweethearting look like in the data?", "Propose generating 5 million rows"],
  train: ["Which method is best and why?", "Did machine learning beat the rule of thumb?", "Propose training all four methods"],
  act: ["Show the top 10 critical alerts", "Plan 120 investigator hours at £28 an hour", "Why was the top alert flagged?"],
  models: ["Compare the methods in plain words", "What drives the model in use?", "Propose exporting the model in use to ONNX"],
  experiments: ["Summarise the last training run", "Which anomaly types does each method miss?", "What would you try next?"],
  assistant: ["What do I have loaded right now?", "Which stores have the most money at risk?", "Who is on your team and what has it cost so far?"],
  exec_overview: ["Summarise the board figures for the last 90 days", "Which stores carry the most revenue at risk?", "Why are cases missing the SLA?"],
  exec_alerts: ["Why was the top alert flagged?", "Which stores need a visit this week?", "Is this theft or a counting mistake?"],
  exec_plan: ["What do 120 investigator hours buy us?", "Is it worth adding more investigators?", "What would it take to run this on our real data?"],
  exec_story: ["What is the business case?", "How does the AI decide, in plain words?", "What would it take to run this on our real data?"],
  settings: ["Who is on your team and what has it cost so far?", "Which model would be cheapest for everyday questions?", "Summarise everything loaded in three lines"],
};

export function AssistantProvider({ children }: { children: ReactNode }) {
  const app = useApp();
  const { page, mode, selectedDatasetId, selectedRunId, selectedAlertId, drill, actTab, activeModel, watchJob, toast, jobs } = app;
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [dockOpen, setDockOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [sessionUsage, setSessionUsage] = useState<SessionUsage | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const notified = useRef<Set<string>>(new Set());
  const sessionRef = useRef<string | null>(null);
  const visibleRef = useRef(false);
  visibleRef.current = dockOpen || page === "assistant";
  sessionRef.current = currentSessionId;

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.assistant.status());
    } catch {
      setStatus(null);
    }
  }, []);
  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.assistant.sessions());
    } catch {
      setSessions([]);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
    void refreshSessions();
  }, [refreshStatus, refreshSessions]);
  useEffect(() => {
    if (page === "settings") void refreshStatus();
  }, [page, refreshStatus]);
  useEffect(() => {
    if (dockOpen) setUnread(0);
  }, [dockOpen, messages.length]);

  const ui = useCallback(
    (): UiState => ({ page, mode, tab: page === "act" ? actTab : null, selected_dataset_id: selectedDatasetId, selected_run_id: selectedRunId, selected_alert_id: selectedAlertId, drill_store_id: drill?.storeId ?? null, drill_sku_id: drill?.skuId ?? null, active_model_id: activeModel?.model_id ?? null, selected_schedule_id: page === "schedules" ? app.selectedScheduleId : null }),
    [page, mode, actTab, selectedDatasetId, selectedRunId, selectedAlertId, drill, activeModel, app.selectedScheduleId],
  );

  const updateLast = useCallback((fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((cur) => {
      if (!cur.length) return cur;
      const last = cur[cur.length - 1];
      if (last.role !== "assistant") return cur;
      return [...cur.slice(0, -1), fn(last)];
    });
  }, []);

  const applyEvent = useCallback(
    (e: ChatEvent) => {
      switch (e.event) {
        case "session":
          if (!sessionRef.current) {
            sessionRef.current = e.data.session_id;
            setCurrentSessionId(e.data.session_id);
          }
          break;
        case "text":
          setMessages((cur) => {
            const last = cur[cur.length - 1];
            if (last && last.role === "assistant" && last.pending && (!last.author || last.author === e.data.author || !last.text)) {
              return [...cur.slice(0, -1), { ...last, author: e.data.author, text: last.text + e.data.delta }];
            }
            // another agent starts speaking: close the previous bubble (only the last one is closed when the stream ends)
            const prev = last && last.role === "assistant" && last.pending ? [...cur.slice(0, -1), { ...last, pending: false, endedAt: Date.now() }] : cur;
            return [...prev, { id: mid(), role: "assistant", author: e.data.author, text: e.data.delta, tools: [], proposals: [], pending: true, startedAt: Date.now() }];
          });
          break;
        case "tool_call":
          updateLast((m) => ({ ...m, author: m.author ?? e.data.author, tools: [...m.tools, { id: e.data.id, name: e.data.name, label: e.data.label, ok: null, summary: null, author: e.data.author, at: Date.now() }] }));
          break;
        case "tool_result":
          updateLast((m) => {
            const tools = [...m.tools];
            const i = tools.findIndex((t) => (e.data.id && t.id === e.data.id) || (t.name === e.data.name && t.ok === null));
            if (i >= 0) tools[i] = { ...tools[i], ok: e.data.ok, summary: e.data.summary, doneAt: Date.now() };
            return { ...m, tools };
          });
          break;
        case "proposal":
          updateLast((m) => ({ ...m, proposals: [...m.proposals.filter((p) => p.proposal_id !== e.data.proposal_id), e.data] }));
          break;
        case "usage":
          setSessionUsage(e.data.session);
          updateLast((m) => {
            const u = m.usage ?? { llm_calls: 0, prompt_tokens: 0, completion_tokens: 0, cost_usd: 0, unpriced: false };
            return { ...m, usage: { llm_calls: u.llm_calls + 1, prompt_tokens: u.prompt_tokens + e.data.prompt_tokens, completion_tokens: u.completion_tokens + e.data.completion_tokens, cost_usd: u.cost_usd + (e.data.cost_usd ?? 0), unpriced: u.unpriced || e.data.cost_usd === null } };
          });
          break;
        case "transfer":
          updateLast((m) => ({ ...m, tools: [...m.tools, { id: null, name: "transfer", label: `Handing over to ${e.data.to.replace(/_/g, " ")}`, ok: true, summary: null, author: e.data.from, to: e.data.to, at: Date.now(), doneAt: Date.now() }] }));
          break;
        case "error":
          updateLast((m) => ({ ...m, error: e.data.message }));
          if (e.data.code === "not_configured") void refreshStatus();
          break;
        case "done":
          break;
        default:
          break;
      }
    },
    [updateLast, refreshStatus],
  );

  const send = useCallback(
    async (text: string, opts?: { system?: boolean }) => {
      const msg = text.trim();
      if (!msg || streaming) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      setMessages((cur) => [
        ...cur,
        { id: mid(), role: opts?.system ? "system" : "user", text: msg, tools: [], proposals: [] },
        { id: mid(), role: "assistant", text: "", tools: [], proposals: [], pending: true, startedAt: Date.now() },
      ]);
      try {
        await streamChat({ session_id: sessionRef.current, message: msg, ui: ui() }, applyEvent, controller.signal);
      } catch (err) {
        if ((err as Error).name !== "AbortError") updateLast((m) => ({ ...m, error: errorMessage(err) }));
      } finally {
        setStreaming(false);
        updateLast((m) => ({ ...m, pending: false, endedAt: Date.now() }));
        // read where the user is now, not when the question was sent (they may have closed the dock meanwhile)
        if (!visibleRef.current) setUnread((u) => u + 1);
        void refreshSessions();
      }
    },
    [streaming, ui, applyEvent, updateLast, refreshSessions],
  );

  const abort = useCallback(() => abortRef.current?.abort(), []);

  const setProposal = useCallback((p: Proposal) => {
    setMessages((cur) => cur.map((m) => (m.proposals.some((x) => x.proposal_id === p.proposal_id) ? { ...m, proposals: m.proposals.map((x) => (x.proposal_id === p.proposal_id ? p : x)) } : m)));
  }, []);

  const confirm = useCallback(
    async (proposalId: string) => {
      try {
        const out = await api.assistant.confirm(proposalId);
        setProposal(out.proposal);
        if (out.job) {
          watchJob(out.job);
          toast(`Started: ${out.job.title}`, "success");
          await send(`[confirmed ${proposalId}] Job ${out.job.job_id} has started: ${out.proposal.title}. Briefly tell me what to expect and what to look at when it finishes.`, { system: true });
        } else if (out.proposal.status === "failed") {
          toast(out.proposal.error ?? "Could not start the job", "error");
        } else {
          toast(`Done: ${out.proposal.title}`, "success");
          await Promise.all([app.refreshModels(), app.refreshConnectors()]);
          await send(`[confirmed ${proposalId}] Done: ${out.proposal.title}.`, { system: true });
        }
      } catch (err) {
        toast(errorMessage(err), "error");
      }
    },
    [send, setProposal, watchJob, toast, app],
  );

  const cancel = useCallback(
    async (proposalId: string) => {
      try {
        const out = await api.assistant.cancel(proposalId);
        setProposal(out.proposal);
      } catch (err) {
        toast(errorMessage(err), "error");
      }
    },
    [setProposal, toast],
  );

  // When a confirmed proposal's job finishes, let the agent know (only when the chat is visible).
  useEffect(() => {
    const visible = dockOpen || page === "assistant";
    if (!visible || streaming) return;
    for (const m of messages) {
      for (const p of m.proposals) {
        if (p.status !== "confirmed" || !p.job_id || notified.current.has(p.job_id)) continue;
        const j = jobs[p.job_id];
        if (j && isTerminal(j.status)) {
          notified.current.add(p.job_id);
          void send(`[job ${p.job_id} ${j.status}] ${p.title}. ${j.status === "done" ? "Summarise what changed and what to look at now." : `It ${j.status}: ${j.error ?? ""}. What should I do?`}`, { system: true });
          return;
        }
      }
    }
  }, [jobs, messages, dockOpen, page, streaming, send]);

  const newSession = useCallback(() => {
    abortRef.current?.abort();
    sessionRef.current = null;
    setCurrentSessionId(null);
    setMessages([]);
    setSessionUsage(null);
  }, []);

  const openSession = useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      try {
        const msgs = await api.assistant.messages(id);
        sessionRef.current = id;
        setCurrentSessionId(id);
        setMessages(msgs);
        api.assistant
          .usage(id)
          .then((r) => setSessionUsage(r.totals))
          .catch(() => setSessionUsage(null));
      } catch (err) {
        toast(errorMessage(err), "error");
      }
    },
    [toast],
  );

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await api.assistant.deleteSession(id);
        if (sessionRef.current === id) newSession();
        await refreshSessions();
      } catch (err) {
        toast(errorMessage(err), "error");
      }
    },
    [newSession, refreshSessions, toast],
  );

  const ACT_QUICK: Record<string, string[]> = {
    alerts: ["Why was the open alert flagged?", "Show the top 10 critical alerts", "Which alerts look like till fraud?"],
    dashboard: ["Which stores and categories have the most money at risk?", "How has the number of alerts changed over the last four weeks?", "Which warehouse team has the most critical alerts?"],
    planner: ["Plan 120 investigator hours at £28 an hour", "Compare 40, 120 and 300 hours", "Which team gets the most work this week?"],
    drill: ["Explain this item's stock story", "Is this item's pattern more like theft or a counting error?", "Find other items in this store with alerts"],
    triage: ["How accurate have our alerts been so far?", "Can we retrain with feedback yet?", "Did feedback improve the model?"],
  };
  const quickPrompts =
    mode === "exec" && QUICK[`exec_${page}`]
      ? QUICK[`exec_${page}`]
      : page === "act"
        ? ACT_QUICK[actTab] ?? QUICK.act
        : QUICK[page] ?? QUICK.overview;

  const value = useMemo<AssistantState>(
    () => ({ status, refreshStatus, sessions, refreshSessions, currentSessionId, messages, streaming, dockOpen, setDockOpen, unread, send, abort, confirm, cancel, newSession, openSession, deleteSession, quickPrompts, sessionUsage }),
    [status, refreshStatus, sessions, refreshSessions, currentSessionId, messages, streaming, dockOpen, unread, send, abort, confirm, cancel, newSession, openSession, deleteSession, quickPrompts, sessionUsage],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAssistant(): AssistantState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAssistant must be used inside AssistantProvider");
  return v;
}
