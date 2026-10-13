import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

export function TechnicalDetails({ title = "Technical details", children, open = false }: { title?: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="tech" open={open}>
      <summary>{title}</summary>
      <div className="tech-body">{children}</div>
    </details>
  );
}

export function NextStep({
  title,
  description,
  cta,
  onClick,
  disabled = false,
  disabledReason,
}: {
  title: string;
  description?: string;
  cta: string;
  onClick: () => void;
  disabled?: boolean;
  disabledReason?: string;
}) {
  return (
    <div className="next-step">
      <div>
        <div className="small muted" style={{ textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
          Next step
        </div>
        <h3 style={{ margin: "2px 0" }}>{title}</h3>
        {description ? <div className="muted">{description}</div> : null}
        {disabled && disabledReason ? <div className="small muted">{disabledReason}</div> : null}
      </div>
      <button className="btn primary" disabled={disabled} onClick={onClick}>
        {cta} <ArrowRight size={16} aria-hidden="true" />
      </button>
    </div>
  );
}
