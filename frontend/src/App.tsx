import { AuthProvider, useAuth } from "./components/AuthProvider";
import SignInPage from "./pages/SignInPage";

function AppContent() {
  const { signedIn, recruiter } = useAuth();

  if (!signedIn) {
    return <SignInPage />;
  }

  // Signed in — show the main app (Jobs page will go here)
  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid #eee",
          paddingBottom: "1rem",
          marginBottom: "2rem",
        }}
      >
        <h1 style={{ margin: 0 }}>Lucid</h1>
        <span>{recruiter?.name}</span>
      </header>
      <p>Jobs dashboard coming next…</p>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
