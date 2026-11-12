import { useEffect, useRef, useState } from "react";
import { useAuth } from "../components/AuthProvider";
import type { JobSummary } from "../services/jobs";
import { listJobs } from "../services/jobs";
import DeleteJobDialog from "../components/DeleteJobDialog";
import "./JobsPage.css";

interface Props {
  onNewJob: () => void;
  onSelectJob: (id: number) => void;
}

export default function JobsPage({ onNewJob, onSelectJob }: Props) {
  const { recruiter, signOut } = useAuth();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<JobSummary | null>(null);
  const [notice, setNotice] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    setLoading(true);
    listJobs()
      .then(setJobs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="jobs-page" style={{ padding: "2rem", fontFamily: "system-ui, sans-serif", maxWidth: 800, margin: "0 auto" }}>
      <header className="jobs-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem" }}>
        <h1 style={{ margin: 0 }}>Lucid</h1>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <span style={{ color: "#666" }}>{recruiter?.name}</span>
          <button onClick={signOut} style={linkBtnStyle}>Sign out</button>
        </div>
      </header>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h2 ref={heading} tabIndex={-1} style={{ margin: 0 }}>Jobs</h2>
        <button onClick={onNewJob} style={primaryBtnStyle}>+ New JD</button>
      </div>

      {loading && <p>Loading…</p>}
      {error && <p role="alert" className="jobs-error">{error}</p>}
      <p role="status" className="jobs-notice">{notice}</p>

      {!loading && jobs.length === 0 && (
        <p style={{ color: "#666" }}>No jobs yet. Create your first JD to get started.</p>
      )}

      {jobs.map((job) => (
        <div key={job.id} className="jobs-card">
          <button type="button" className="jobs-open" onClick={() => onSelectJob(job.id)} aria-label={`Open ${job.title}`}>
          <span className="jobs-identity">
            <strong>{job.title}</strong>
            {job.company && <span style={{ color: "#666", marginLeft: "0.5rem" }}>— {job.company}</span>}
          </span>
          <span className="jobs-metadata">
            {job.folder_pdf_count != null && (
              <span style={{ color: "#666", fontSize: "0.875rem" }}>
                {job.folder_pdf_count} PDFs
              </span>
            )}
            <span style={statusBadgeStyle(job.status)}>{job.status}</span>
          </span>
          </button>
          <button type="button" className="jobs-delete" aria-label={`Delete ${job.title}`} onClick={() => { setNotice(""); setDeleting(job); }}>Delete</button>
        </div>
      ))}
      {deleting && <DeleteJobDialog job={deleting} onCancel={() => setDeleting(null)} onDeleted={() => {
        setJobs((current) => current.filter((job) => job.id !== deleting.id));
        setNotice(`Deleted “${deleting.title}”.`);
        setDeleting(null);
        heading.current?.focus();
      }} />}
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
