import { useEffect, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import { useJob } from "../hooks/useJob";
import type { OnnxStatus } from "../types";
import { JobProgress } from "./JobProgress";
import { Spinner } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";
import { fmtBytes } from "../utils";

/** Download bundle + ONNX export controls for one model. */
export function ModelExport({ modelId, modelKey }: { modelId: string; modelKey: string }) {
  const { toast } = useApp();
  const [status, setStatus] = useState<OnnxStatus | null>(null);
  const refresh = () => api.models.onnxStatus(modelId).then(setStatus).catch(() => setStatus(null));
  const { job, running, setJob } = useJob(null, {
    onDone: () => {
      void refresh();
      toast("ONNX model ready", "success");
    },
    onFail: (j) => {
      void refresh();
      toast(j.error ?? "ONNX export failed", "error");
    },
  });
  useEffect(() => {
    void refresh();
  }, [modelId]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    try {
      setJob(await api.models.exportOnnx(modelId));
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  return (
    <div className="card subtle">
      <div className="card-title">
        <h3>Use this model elsewhere</h3>
      </div>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 280px" }}>
          <a className="btn primary" href={api.models.exportUrl(modelId)} download>
            Download model bundle (.zip)
          </a>
          <div className="small muted" style={{ marginTop: 6 }}>
            model.joblib, model.json, the feature and detector code, predict.py and pinned requirements{status?.ready ? ", plus model.onnx" : ""}. Score any daily CSV with <code>python predict.py daily.csv scored.csv --skus skus.csv</code>.
          </div>
        </div>
        <div style={{ flex: "1 1 320px" }}>
          {status?.ready ? (
            <>
              <div className="row">
                <span className="chip status-done">ONNX ready</span>
                <a className="btn" href={api.models.onnxUrl(modelId)} download>
                  Download model.onnx ({fmtBytes(status.size_bytes)})
                </a>
                <button className="btn sm" disabled={running} onClick={start} title="Build again">
                  Rebuild
                </button>
              </div>
              <div className="small muted" style={{ marginTop: 6 }}>
                Checked on {status.n_checked ?? 0} sample days: rankings agree {status.spearman !== null ? `(rank correlation ${status.spearman.toFixed(4)}, top-1% overlap ${Math.round((status.top1_overlap ?? 0) * 100)}%)` : ""}. Runs with onnxruntime in Python, C#, Java, JavaScript or C++.
              </div>
            </>
          ) : status && !status.available ? (
            <div className="alert info small">ONNX export is not available for this model: {status.reason}</div>
          ) : (
            <>
              <button className="btn" disabled={running || !status} onClick={start}>
                {running ? <Spinner /> : null}
                {running ? "Building…" : "Export to ONNX"}
              </button>
              <div className="small muted" style={{ marginTop: 6 }}>
                Builds the whole scoring graph (feature selection, scaling and detector) as one ONNX file and checks it ranks sample days exactly like the original. A few seconds.
              </div>
            </>
          )}
          {job ? (
            <div className="mt">
              <JobProgress job={job} compact />
            </div>
          ) : null}
          {status?.warnings.length ? (
            <ul className="small muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {status.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      <TechnicalDetails title="Code to load it">
        <pre className="code-block">{`import joblib, json, numpy as np
import features as F, detectors       # both ship in the bundle
pipe = joblib.load("model.joblib")
meta = json.load(open("model.json"))
X = F.matrix(engineered_features, meta["feature_columns"])   # see predict.py for engineering
score = detectors.pipeline_score(pipe, X)                     # higher = more unusual
alert = score >= meta["thresholds"]["alert"]

# ONNX: one float32 input "features" [n, ${"{"}len(meta["feature_columns"]){"}"}], output "anomaly_score"
import onnxruntime as ort
score = ort.InferenceSession("model.onnx").run(None, {"features": X.astype(np.float32)})[0]`}</pre>
        <div className="small muted">
          Method key <code>{modelKey}</code>. The joblib file needs the versions in requirements.txt; the ONNX file needs only onnxruntime.
        </div>
      </TechnicalDetails>
    </div>
  );
}
