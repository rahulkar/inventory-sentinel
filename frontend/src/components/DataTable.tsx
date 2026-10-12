import { featureLabel, fmtFeatureValue, fmtNum } from "../utils";

interface Props {
  columns: string[];
  rows: Record<string, unknown>[];
  maxHeight?: number;
  highlight?: string[];
  stickyFirst?: boolean;
  plainHeaders?: boolean;
}

export function DataTable({ columns, rows, maxHeight = 380, highlight = [], stickyFirst = false, plainHeaders = false }: Props) {
  if (!rows.length) return <div className="empty">No rows to show.</div>;
  const numeric = new Set(columns.filter((c) => rows.some((r) => typeof r[c] === "number")));
  return (
    <div className={`table-wrap ${stickyFirst ? "sticky-first" : ""}`} style={{ maxHeight }}>
      <table className="data">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} className={numeric.has(c) ? "num" : ""} style={highlight.includes(c) ? { color: "var(--primary)" } : undefined} title={c}>
                {plainHeaders ? featureLabel(c) : c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c} className={numeric.has(c) ? "num" : ""}>
                  {plainHeaders ? fmtFeatureValue(c, r[c]) : fmtNum(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
