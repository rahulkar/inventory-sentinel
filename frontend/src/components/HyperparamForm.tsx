import type { ParamSpec } from "../types";

interface Props {
  params: ParamSpec[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}

export function HyperparamForm({ params, values, onChange }: Props) {
  if (!params.length) return <div className="small muted" style={{ marginLeft: 23, marginTop: 6 }}>No hyperparameters.</div>;
  return (
    <div className="params">
      {params.map((p) => {
        const v = values[p.name] ?? p.default;
        if (p.type === "bool") {
          return (
            <label key={p.name} className="check">
              <input type="checkbox" checked={Boolean(v)} onChange={(e) => onChange(p.name, e.target.checked)} />
              {p.label}
            </label>
          );
        }
        if (p.type === "select") {
          return (
            <label key={p.name} className="field">
              {p.label}
              <select value={String(v)} onChange={(e) => onChange(p.name, e.target.value)}>
                {(p.options ?? []).map((o) => (
                  <option key={String(o)} value={String(o)}>
                    {String(o)}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        return (
          <label key={p.name} className="field">
            <span>
              {p.label}
              {p.help ? <span className="hint"> · {p.help}</span> : null}
            </span>
            <input
              type="number"
              value={String(v)}
              min={p.min ?? undefined}
              max={p.max ?? undefined}
              step={p.step ?? (p.type === "int" ? 1 : 0.01)}
              onChange={(e) => onChange(p.name, e.target.value === "" ? p.default : Number(e.target.value))}
            />
          </label>
        );
      })}
    </div>
  );
}
