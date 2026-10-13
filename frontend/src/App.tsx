import { AppProvider, useApp } from "./context";
import { AssistantProvider } from "./assistant/AssistantContext";
import { Layout } from "./components/Layout";
import { OverviewPage } from "./pages/OverviewPage";
import { DataPage } from "./pages/DataPage";
import { TrainPage } from "./pages/TrainPage";
import { ActPage } from "./pages/ActPage";
import { ModelsPage } from "./pages/ModelsPage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { StoryPage } from "./pages/StoryPage";
import { AssistantPage } from "./pages/AssistantPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SchedulesPage } from "./pages/SchedulesPage";
import { ExecutivePage } from "./pages/ExecutivePage";
import { ExecAlertsPage, ExecPlanPage } from "./pages/ExecPages";

function Router() {
  const { page, mode } = useApp();
  switch (page) {
    case "alerts":
      return <ExecAlertsPage />;
    case "plan":
      return <ExecPlanPage />;
    case "story":
      return <StoryPage />;
    case "data":
      return <DataPage />;
    case "train":
      return <TrainPage />;
    case "act":
      return <ActPage />;
    case "schedules":
      return <SchedulesPage />;
    case "models":
      return <ModelsPage />;
    case "experiments":
      return <ExperimentsPage />;
    case "assistant":
      return <AssistantPage />;
    case "settings":
      return <SettingsPage />;
    default:
      return mode === "exec" ? <ExecutivePage /> : <OverviewPage />;
  }
}

export default function App() {
  return (
    <AppProvider>
      <AssistantProvider>
        <Layout>
          <Router />
        </Layout>
      </AssistantProvider>
    </AppProvider>
  );
}
