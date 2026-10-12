import { useApp } from "../context";
import { TechnicalDetails } from "./TechnicalDetails";
import { featureLabel } from "../utils";

/** Plain-language names for hyperparameters that the registry does not label (fallbacks). */
const PARAM_FALLBACK: Record<string, string> = {
  max_samples: "Rows per tree",
  n_neighbors: "Neighbours",
  reference_size: "Reference rows",
  hidden: "Layers",
  min_mad: "Minimum spread",
  classifier: "Feedback classifier",
  max_iter: "Training passes",
  n_estimators: "Number of trees",
  learning_rate: "Learning rate",
  max_depth: "Maximum tree depth",
  l2_regularization: "L2 regularisation",
  alpha: "Regularisation strength",
  num_leaves: "Leaves per tree",
  min_samples_leaf: "Minimum rows per leaf",
  subsample: "Row sampling",
  colsample_bytree: "Column sampling",
  min_child_weight: "Minimum leaf weight",
  reg_lambda: "L2 regularisation",
  max_features: "Features per split",
};

function humanise(name: string): string {
  return PARAM_FALLBACK[name] ?? name.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function fmtParam(name: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "default";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number" && v === 0) {
    if (/depth|max_|leaf|leaves/.test(name)) return "0 (no limit)";
    if (/regular|alpha|lambda|penalty/.test(name)) return "0 (none)";
    return "0";
  }
  return String(v);
}

/** Hyperparameters with the same labels as the Train screen, raw names on hover. */
export function ParamList({ modelKey, params }: { modelKey: string; params: Record<string, unknown> }) {
  const { availableModels } = useApp();
  const spec = availableModels.find((m) => m.key === modelKey);
  const entries = Object.entries(params);
  if (!entries.length) return <div className="small muted">None: this algorithm has no tunable settings.</div>;
  return (
    <dl className="kv">
      {entries.map(([k, v]) => {
        const p = spec?.params.find((x) => x.name === k);
        return (
          <div key={k} style={{ display: "contents" }}>
            <dt title={k}>{p?.label ?? humanise(k)}</dt>
            <dd>{fmtParam(k, v)}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/** Feature chips in plain language; the raw column names live under "Technical details". */
export function FeatureChips({ features }: { features: string[] }) {
  if (!features.length) return <div className="small muted">No features recorded.</div>;
  return (
    <>
      <div className="feature-chips">
        {features.map((f) => (
          <span key={f} className="chip neutral" title={f}>
            {featureLabel(f)}
          </span>
        ))}
      </div>
      <TechnicalDetails title="Column names">
        <div className="small mono muted" style={{ overflowWrap: "anywhere" }}>
          {features.join(", ")}
        </div>
      </TechnicalDetails>
    </>
  );
}
