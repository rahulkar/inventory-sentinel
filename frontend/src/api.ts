import type {
  Alert,
  AlertPage,
  AppConfig,
  AssistantStatus,
  ChatEvent,
  ChatMessage,
  ChatRequest,
  Dashboard,
  DatasetMeta,
  DetectionRun,
  DetectionRunSummary,
  DocSearchHit,
  DocumentLibrary,
  LibraryDocument,
  ExecutiveSummary,
  Experiment,
  AlertSop,
  Connector,
  ConnectorIn,
  ConnectorTest,
  ExportStatus,
  Health,
  InvestigationPlan,
  Job,
  LlmSettingsOut,
  LlmTestResult,
  ModelMeta,
  ModelSpec,
  ModelSummary,
  OnnxStatus,
  Outcome,
  Overview,
  PlanRequest,
  PreviewResponse,
  PreviewTable,
  Proposal,
  Schedule,
  ScheduleIn,
  SchedulerStatus,
  ScheduleRun,
  Sop,
  SopSummary,
  StockPosition,
  VendorTask,
  VendorTaskDraft,
  VendorTaskResult,
  SeriesMatch,
  SeriesResponse,
  SessionSummary,
  TrainJob,
  TrainRequest,
  TriageRecord,
  TriageSummary,
  UsageReport,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

function detailOf(body: unknown, fallback: string): string {
  const b = body as { detail?: unknown } | null;
  if (typeof b?.detail === "string") return b.detail;
  if (Array.isArray(b?.detail)) return (b!.detail as { msg: string }[]).map((d) => d.msg).join("; ");
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detailOf(body, `${res.status} ${res.statusText}`));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function json(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

function form(fields: Record<string, string | number | null | undefined>, file: File): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) {
    if (v !== null && v !== undefined && v !== "") fd.append(k, String(v));
  }
  fd.append("file", file);
  return fd;
}

/** POST a FormData with upload progress (fraction 0..1). */
export function xhrForm<T>(path: string, fd: FormData, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new ApiError(xhr.status, detailOf(body, `${xhr.status} ${xhr.statusText}`)));
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.send(fd);
  });
}

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export interface AlertQuery {
  severity?: string[];
  likely_type?: string[];
  store_id?: string | null;
  team?: string | null;
  category?: string | null;
  status?: string | null;
  q?: string | null;
  sort?: string;
  limit?: number;
  offset?: number;
  answer_key?: boolean;
}

export interface ExecFilters {
  days: number;
  region?: string | null;
  store_id?: string | null;
  category?: string | null;
}

export function planQuery(p: Omit<PlanRequest, "run_id">, team?: string | null): string {
  return qs({ hours: p.hours, hourly_cost: p.hourly_cost, recovery_rate: p.recovery_rate, horizon_days: p.horizon_days, team, severities: p.severities ?? undefined, teams: p.teams ?? undefined });
}

export const api = {
  health: () => request<Health>("/api/health"),
  config: () => request<AppConfig>("/api/config"),
  overview: () => request<Overview>("/api/overview"),
  experiments: () => request<Experiment[]>("/api/experiments"),

  jobs: {
    list: (active = false, type?: string) => request<Job[]>(`/api/jobs?active=${active}${type ? `&type=${type}` : ""}`),
    get: (id: string) => request<Job>(`/api/jobs/${id}`),
    cancel: (id: string) => request<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  },

  datasets: {
    list: () => request<DatasetMeta[]>("/api/datasets"),
    get: (id: string) => request<DatasetMeta>(`/api/datasets/${id}`),
    upload: (file: File, fields: { name?: string; column_map?: string }, onProgress?: (f: number) => void) => xhrForm<Job>("/api/datasets/upload", form(fields, file), onProgress),
    configure: (id: string, column_map: Record<string, string>, name?: string) => request<Job>(`/api/datasets/${id}/configure`, json("POST", { column_map, name })),
    preview: (id: string, table: PreviewTable, rows = 50, offset = 0, answerKey = false) => request<PreviewResponse>(`/api/datasets/${id}/preview${qs({ table, rows, offset, answer_key: answerKey || undefined })}`),
    downloadUrl: (id: string, table: "stores" | "skus" | "lp_flags") => `/api/datasets/${id}/download?table=${table}`,
    delete: (id: string) => request<{ deleted: boolean }>(`/api/datasets/${id}`, { method: "DELETE" }),
    export: (id: string) => request<Job>(`/api/datasets/${id}/export`, { method: "POST" }),
    exportStatus: (id: string) => request<ExportStatus>(`/api/datasets/${id}/export`),
    exportUrl: (id: string) => `/api/datasets/${id}/export/download`,
  },

  connectors: {
    list: () => request<Connector[]>("/api/connectors"),
    get: (id: string) => request<Connector>(`/api/connectors/${id}`),
    create: (body: ConnectorIn) => request<Connector>("/api/connectors", json("POST", body)),
    update: (id: string, body: ConnectorIn) => request<Connector>(`/api/connectors/${id}`, json("PUT", body)),
    delete: (id: string) => request<{ deleted: boolean }>(`/api/connectors/${id}`, { method: "DELETE" }),
    testDraft: (body: ConnectorIn, connectorId?: string | null) => request<ConnectorTest>(`/api/connectors/test${qs({ connector_id: connectorId })}`, json("POST", body)),
    test: (id: string) => request<ConnectorTest>(`/api/connectors/${id}/test`, { method: "POST" }),
    sync: (id: string, full = false) => request<Job>(`/api/connectors/${id}/sync${qs({ full: full || undefined })}`, { method: "POST" }),
    lookup: (id: string, storeId: string, skuId: string, days = 7) => request<StockPosition>(`/api/connectors/${id}/lookup${qs({ store_id: storeId, sku_id: skuId, days })}`),
    tasks: (id: string, status?: string | null, refresh = false) => request<VendorTask[]>(`/api/connectors/${id}/tasks${qs({ status, refresh: refresh || undefined })}`),
  },

  schedules: {
    list: () => request<Schedule[]>("/api/schedules"),
    status: () => request<SchedulerStatus>("/api/schedules/status"),
    create: (body: ScheduleIn) => request<Schedule>("/api/schedules", json("POST", body)),
    update: (id: string, body: ScheduleIn) => request<Schedule>(`/api/schedules/${id}`, json("PUT", body)),
    preview: (body: ScheduleIn) => request<{ summary: string; next_runs: string[] }>("/api/schedules/preview", json("POST", body)),
    setEnabled: (id: string, enabled: boolean) => request<Schedule>(`/api/schedules/${id}/enabled?enabled=${enabled}`, { method: "POST" }),
    delete: (id: string) => request<{ deleted: boolean }>(`/api/schedules/${id}`, { method: "DELETE" }),
    run: (id: string) => request<{ run: ScheduleRun; job: Job | null }>(`/api/schedules/${id}/run`, { method: "POST" }),
    runs: (id?: string | null, limit = 30) => request<ScheduleRun[]>(id ? `/api/schedules/${id}/runs?limit=${limit}` : `/api/schedules/runs?limit=${limit}`),
    pendingApprovals: () => request<Proposal[]>("/api/schedules/pending-approvals"),
  },

  sops: {
    list: () => request<SopSummary[]>("/api/sops"),
    get: (id: string) => request<Sop>(`/api/sops/${id}`),
    forAlert: (runId: string, alertId: string) => request<AlertSop>(`/api/runs/${runId}/alerts/${alertId}/sop`),
  },

  vendorTasks: {
    list: (q: { alert_key?: string | null; run_id?: string | null; connector_id?: string | null; status?: string | null } = {}) => request<VendorTask[]>(`/api/vendor-tasks${qs(q)}`),
    raise: (tasks: VendorTaskDraft[], connectorId?: string | null) => request<VendorTaskResult>("/api/vendor-tasks", json("POST", { tasks, connector_id: connectorId ?? null })),
  },

  models: {
    available: () => request<ModelSpec[]>("/api/models/available"),
    list: () => request<ModelSummary[]>("/api/models"),
    get: (id: string) => request<ModelMeta>(`/api/models/${id}`),
    active: () => request<ModelMeta | null>("/api/models/active"),
    activate: (id: string) => request<ModelSummary>(`/api/models/${id}/activate`, { method: "POST" }),
    delete: (id: string) => request<{ deleted: boolean }>(`/api/models/${id}`, { method: "DELETE" }),
    exportUrl: (id: string) => `/api/models/${id}/export`,
    onnxStatus: (id: string) => request<OnnxStatus>(`/api/models/${id}/onnx`),
    exportOnnx: (id: string) => request<Job>(`/api/models/${id}/export/onnx`, { method: "POST" }),
    onnxUrl: (id: string) => `/api/models/${id}/onnx/download`,
    retrain: (id: string, alpha = 0.4) => request<Job>(`/api/models/${id}/retrain-feedback`, json("POST", { alpha })),
  },

  train: {
    start: (req: TrainRequest) => request<Job>("/api/train", json("POST", req)),
    get: (jobId: string) => request<TrainJob>(`/api/train/${jobId}`),
  },

  runs: {
    detect: (datasetId: string, modelId?: string | null) => request<Job>("/api/detect", json("POST", { dataset_id: datasetId, model_id: modelId ?? null })),
    list: (datasetId?: string | null) => request<DetectionRunSummary[]>(`/api/runs${qs({ dataset_id: datasetId })}`),
    get: (id: string) => request<DetectionRun>(`/api/runs/${id}`),
    delete: (id: string) => request<{ deleted: boolean }>(`/api/runs/${id}`, { method: "DELETE" }),
    dashboard: (id: string) => request<Dashboard>(`/api/runs/${id}/dashboard`),
    executive: (id: string, f: ExecFilters) => request<ExecutiveSummary>(`/api/runs/${id}/executive${qs({ ...f })}`),
    alerts: (id: string, q: AlertQuery = {}) => request<AlertPage>(`/api/runs/${id}/alerts${qs({ ...q })}`),
    alert: (id: string, alertId: string, answerKey = false) => request<Alert>(`/api/runs/${id}/alerts/${alertId}${qs({ answer_key: answerKey || undefined })}`),
    alertsCsvUrl: (id: string) => `/api/runs/${id}/alerts.csv`,
    series: (id: string, storeId: string, skuId: string, answerKey = false) => request<SeriesResponse>(`/api/runs/${id}/series${qs({ store_id: storeId, sku_id: skuId, answer_key: answerKey || undefined })}`),
    search: (id: string, q: string) => request<SeriesMatch[]>(`/api/runs/${id}/search${qs({ q })}`),
    recalibrate: (id: string) => request<{ reviewed: number; precision: number }>(`/api/runs/${id}/recalibrate`, { method: "POST" }),
  },

  planner: {
    plan: (req: PlanRequest) => request<InvestigationPlan>("/api/plan", json("POST", req)),
    worklistCsvUrl: (runId: string, p: Omit<PlanRequest, "run_id">, team?: string | null) => `/api/plan/${runId}/worklist.csv${planQuery(p, team)}`,
    worklistZipUrl: (runId: string, p: Omit<PlanRequest, "run_id">) => `/api/plan/${runId}/worklist.zip${planQuery(p)}`,
  },

  triage: {
    decide: (runId: string, alertId: string, outcome: Outcome, note?: string) => request<{ saved: TriageRecord[] }>("/api/triage", json("POST", { run_id: runId, alert_id: alertId, outcome, note: note || null })),
    bulk: (runId: string, alertIds: string[], outcome: Outcome) => request<{ saved: TriageRecord[] }>("/api/triage/bulk", json("POST", { run_id: runId, alert_ids: alertIds, outcome })),
    list: (datasetId: string) => request<TriageRecord[]>(`/api/triage?dataset_id=${datasetId}`),
    summary: (datasetId: string, runId?: string | null) => request<TriageSummary>(`/api/triage/summary${qs({ dataset_id: datasetId, run_id: runId })}`),
    simulate: (runId: string, days = 5, perDay = 25) => request<{ reviewed: number; true_alerts: number; precision: number }>("/api/triage/simulate", json("POST", { run_id: runId, days, per_day: perDay })),
    reset: (datasetId: string) => request<{ removed: number }>(`/api/triage?dataset_id=${datasetId}`, { method: "DELETE" }),
  },

  documents: {
    list: () => request<DocumentLibrary>("/api/documents"),
    upload: (file: File, kind: "auto" | "sop" | "reference", onProgress?: (f: number) => void) => xhrForm<LibraryDocument>("/api/documents", form({ kind }, file), onProgress),
    delete: (id: string) => request<{ deleted: boolean }>(`/api/documents/${id}`, { method: "DELETE" }),
    search: (q: string, k = 5) => request<{ hits: DocSearchHit[]; mode: string }>(`/api/documents/search${qs({ q, k })}`),
    reindex: () => request<{ started: boolean }>("/api/documents/reindex", { method: "POST" }),
    fileUrl: (id: string) => `/api/documents/${id}/file`,
  },

  settings: {
    llm: {
      get: () => request<LlmSettingsOut>("/api/settings/llm"),
      put: (body: Record<string, unknown>) => request<LlmSettingsOut>("/api/settings/llm", json("PUT", body)),
      test: (body: { base_url?: string; api_key?: string; model?: string | null; verify_ssl?: boolean; ca_bundle?: string }) => request<LlmTestResult>("/api/settings/llm/test", json("POST", body)),
      models: () => request<{ models: string[] }>("/api/settings/llm/models"),
    },
  },

  assistant: {
    status: () => request<AssistantStatus>("/api/assistant/status"),
    sessions: () => request<SessionSummary[]>("/api/assistant/sessions"),
    messages: (id: string) => request<ChatMessage[]>(`/api/assistant/sessions/${id}/messages`),
    deleteSession: (id: string) => request<{ deleted: boolean }>(`/api/assistant/sessions/${id}`, { method: "DELETE" }),
    proposals: (sessionId?: string | null) => request<Proposal[]>(`/api/assistant/proposals${sessionId ? `?session_id=${sessionId}` : ""}`),
    confirm: (id: string) => request<{ proposal: Proposal; job: Job | null; result: Record<string, unknown> | null }>(`/api/assistant/proposals/${id}/confirm`, { method: "POST" }),
    cancel: (id: string) => request<{ proposal: Proposal }>(`/api/assistant/proposals/${id}/cancel`, { method: "POST" }),
    usage: (sessionId?: string | null) => request<UsageReport>(`/api/assistant/usage${sessionId ? `?session_id=${sessionId}` : ""}`),
    resetUsage: () => request<{ reset: boolean }>("/api/assistant/usage", { method: "DELETE" }),
  },
};

/** POST a chat turn and consume the server-sent event stream. */
export async function streamChat(body: ChatRequest, onEvent: (e: ChatEvent) => void, signal: AbortSignal): Promise<void> {
  const res = await fetch("/api/assistant/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!res.ok || !res.body) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detailOf(parsed, `${res.status} ${res.statusText}`));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!frame.trim() || frame.startsWith(":")) continue;
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      try {
        onEvent({ event, data: JSON.parse(data) } as ChatEvent);
      } catch {
        /* malformed frame */
      }
    }
  }
}
