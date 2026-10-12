import { useApp } from "../context";
import { AlertQueue } from "../components/AlertQueue";
import { InvestigationPlanner } from "../components/InvestigationPlanner";
import { EmptyState, InvestigationArt, AlertBellArt } from "../components/Illustrations";
import type { ReactNode } from "react";

/** Executive mode: Alerts and Plan without run pickers, filters or statistics. */
function useRun() {
  const { runs, selectedRunId, datasets } = useApp();
  const run = runs.find((r) => r.run_id === selectedRunId) ?? runs[0] ?? null;
  const ds = run ? datasets.find((d) => d.id === run.dataset_id) : null;
  return { run, hasTruth: !!ds?.has_truth };
}

function NoRun({ art, what }: { art: ReactNode; what: string }) {
  const { setPage } = useApp();
  return (
    <div className="card">
      <EmptyState art={art}>
        <b>Nothing to {what} yet.</b>
        <div className="muted">Run the pipeline from the Overview first; it takes about a minute.</div>
        <button className="btn primary mt" onClick={() => setPage("overview")}>
          Go to Overview
        </button>
      </EmptyState>
    </div>
  );
}

export function ExecAlertsPage() {
  const { run, hasTruth } = useRun();
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Alerts</h1>
          <p>Each alert is one item in one store that looks wrong, with the reasons and the money at stake. Click one to see why, and record what the team found.</p>
        </div>
      </div>
      {run ? <AlertQueue runId={run.run_id} datasetHasTruth={hasTruth} simple /> : <NoRun art={<AlertBellArt />} what="review" />}
    </div>
  );
}

export function ExecPlanPage() {
  const { run } = useRun();
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Plan the investigators' week</h1>
          <p>Investigator time is the scarce resource. Choose the hours; the model picks the alerts that recover the most per hour.</p>
        </div>
      </div>
      {run ? <InvestigationPlanner runId={run.run_id} simple /> : <NoRun art={<InvestigationArt />} what="plan" />}
    </div>
  );
}
