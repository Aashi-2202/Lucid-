import { useEffect, useState } from "react";

function App() {
  const [backendStatus, setBackendStatus] = useState<string>("checking...");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.status))
      .catch(() => setBackendStatus("offline — starting up"));
  }, []);

  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
      <h1>Lucid</h1>
      <p>AI-powered resume screening</p>
      <p>
        Backend: <strong>{backendStatus}</strong>
      </p>
    </div>
  );
}

export default App;
