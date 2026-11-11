import { useState } from "react";
import { AuthProvider, useAuth } from "./components/AuthProvider";
import SignInPage from "./pages/SignInPage";
import JobsPage from "./pages/JobsPage";
import JobSetupPage from "./pages/JobSetupPage";
import AssessmentPage from "./pages/AssessmentPage";

type Page =
  | { view: "jobs" }
  | { view: "new-job" }
  | { view: "edit-job"; jobId: number }
  | { view: "assessment"; jobId:number; assessmentId:string };

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
          onAssessment={(assessmentId,jobId)=>setPage({view:"assessment",jobId,assessmentId})}
        />
      );
    case "edit-job":
      return (
        <JobSetupPage
          jobId={page.jobId}
          onBack={() => setPage({ view: "jobs" })}
          onAssessment={(assessmentId,jobId)=>setPage({view:"assessment",jobId,assessmentId})}
        />
      );
    case "assessment":
      return <AssessmentPage assessmentId={page.assessmentId} onBack={()=>setPage({view:"edit-job",jobId:page.jobId})} />;
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
