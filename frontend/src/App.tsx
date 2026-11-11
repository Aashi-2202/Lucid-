import { useState } from "react";
import { AuthProvider, useAuth } from "./components/AuthProvider";
import SignInPage from "./pages/SignInPage";
import JobsPage from "./pages/JobsPage";
import JobSetupPage from "./pages/JobSetupPage";

type Page =
  | { view: "jobs" }
  | { view: "new-job" }
  | { view: "edit-job"; jobId: number };

function AppContent() {
  const { signedIn } = useAuth();
  const [page, setPage] = useState<Page>({ view: "jobs" });

  if (!signedIn) {
    return <SignInPage />;
  }

  switch (page.view) {
    case "jobs":
      return (
        <JobsPage
          onNewJob={() => setPage({ view: "new-job" })}
          onSelectJob={(id) => setPage({ view: "edit-job", jobId: id })}
        />
      );
    case "new-job":
      return (
        <JobSetupPage
          onBack={() => setPage({ view: "jobs" })}
        />
      );
    case "edit-job":
      return (
        <JobSetupPage
          jobId={page.jobId}
          onBack={() => setPage({ view: "jobs" })}
        />
      );
  }
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
