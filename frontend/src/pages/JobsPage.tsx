import { useEffect, useState } from "react";
import { useAuth } from "../components/AuthProvider";
import type { JobSummary } from "../services/jobs";
import { listJobs } from "../services/jobs";

interface Props {
  onNewJob: () => void;
  onSelectJob: (id: number) => void;
}

export default function JobsPage({ onNewJob, onSelectJob }: Props) {
  const { recruiter, signOut } = useAuth();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    listJobs()
      .then(setJobs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif", maxWidth: 800, margin: "0 auto" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem" }}>
        <h1 style={{ margin: 0 }}>Lucid</h1>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <span style={{ color: "#666" }}>{recruiter?.name}</span>
          <button onClick={signOut} style={linkBtnStyle}>Sign out</button>
        </div>
      </header>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h2 style={{ margin: 0 }}>Jobs</h2>
        <button onClick={onNewJob} style={primaryBtnStyle}>+ New JD</button>
      </div>

      {loading && <p>Loading…</p>}
      {error && <p style={{ color: "#c00" }}>{error}</p>}

      {!loading && jobs.length === 0 && (
        <p style={{ color: "#666" }}>No jobs yet. Create your first JD to get started.</p>
      )}

      {jobs.map((job) => (
        <div
          key={job.id}
          onClick={() => onSelectJob(job.id)}
          style={jobCardStyle}
        >
          <div style={{ flex: 1 }}>
            <strong>{job.title}</strong>
            {job.company && <span style={{ color: "#666", marginLeft: "0.5rem" }}>— {job.company}</span>}
          </div>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
            {job.folder_pdf_count != null && (
              <span style={{ color: "#666", fontSize: "0.875rem" }}>
                {job.folder_pdf_count} PDFs
              </span>
            )}
            <span style={statusBadgeStyle(job.status)}>{job.status}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────

const primaryBtnStyle: React.CSSProperties = {
  padding: "0.5rem 1.25rem",
  background: "#2563eb",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.9rem",
  fontWeight: 500,
};

const linkBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#2563eb",
  cursor: "pointer",
  fontSize: "0.875rem",
};

const jobCardStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "1rem 1.25rem",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  marginBottom: "0.75rem",
  cursor: "pointer",
  transition: "border-color 0.15s",
};

function statusBadgeStyle(status: string): React.CSSProperties {
  const colors: Record<string, { bg: string; fg: string }> = {
    draft: { bg: "#f3f4f6", fg: "#374151" },
    active: { bg: "#dbeafe", fg: "#1d4ed8" },
    completed: { bg: "#dcfce7", fg: "#15803d" },
  };
  const c = colors[status] ?? colors.draft;
  return {
    padding: "0.2rem 0.6rem",
    borderRadius: 12,
    fontSize: "0.75rem",
    fontWeight: 500,
    background: c.bg,
    color: c.fg,
  };
}
