import { useState, useEffect } from "react";
import {
  createJob,
  getJob,
  updateJob,
  checkFolder,
  setSkills,
  getServiceAccountEmail,
} from "../services/jobs";
import type { JobDetail, FolderCheckResult } from "../services/jobs";
import type { SkillRequirement } from "../types";

interface Props {
  jobId?: number; // If provided, edit existing; otherwise create new
  onBack: () => void;
}

// ── Evidence level labels ───────────────────────────────────────
const EVIDENCE_LABELS: Record<number, string> = {
  1: "Mention/basic",
  2: "Coursework/program",
  3: "Applied project",
  4: "Internship",
  5: "Relevant work experience",
};

const IMPORTANCE_LABELS: Record<number, string> = {
  1: "Nice to have",
  2: "Low",
  3: "Moderate",
  4: "High",
  5: "Critical",
};

// ── Empty skill template ────────────────────────────────────────
function emptySkill(): SkillInput {
  return {
    skill: "",
    description: "",
    mandatory: false,
    importance: 3,
    required_evidence_level: 1,
    assessment_method: "resume" as const,
    aliases: [],
  };
}

type SkillInput = Omit<SkillRequirement, "id">;

export default function JobSetupPage({ jobId, onBack }: Props) {
  // ── Job fields ────────────────────────────────────────────────
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [folderLink, setFolderLink] = useState("");
  const [company, setCompany] = useState("");
  const [savedJob, setSavedJob] = useState<JobDetail | null>(null);

  // ── Folder check ──────────────────────────────────────────────
  const [folderResult, setFolderResult] = useState<FolderCheckResult | null>(null);
  const [checkingFolder, setCheckingFolder] = useState(false);

  // ── Service account email ─────────────────────────────────────
  const [saEmail, setSaEmail] = useState<string>("");
  const [copiedEmail, setCopiedEmail] = useState(false);

  // ── Skills ────────────────────────────────────────────────────
  const [skills, setSkillsList] = useState<SkillInput[]>([emptySkill()]);
  const [savingSkills, setSavingSkills] = useState(false);

  // ── General state ─────────────────────────────────────────────
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Load existing job ─────────────────────────────────────────
  useEffect(() => {
    if (jobId) {
      getJob(jobId).then((job) => {
        setSavedJob(job);
        setTitle(job.title);
        setDescription(job.description);
        setFolderLink(job.folder_link);
        setCompany(job.company ?? "");
        if (job.skills.length > 0) {
          setSkillsList(
            job.skills.map((s) => ({
              skill: s.skill,
              description: s.description ?? "",
              mandatory: s.mandatory,
              importance: s.importance,
              required_evidence_level: s.required_evidence_level,
              assessment_method: s.assessment_method,
              aliases: s.aliases ?? [],
            }))
          );
        }
        if (job.folder_name) {
          setFolderResult({
            success: true,
            folder_name: job.folder_name,
            pdf_count: job.folder_pdf_count,
            error: null,
          });
        }
      });
    }
    // Load service account email
    getServiceAccountEmail()
      .then((r) => setSaEmail(r.email))
      .catch(() => {}); // Non-critical
  }, [jobId]);

  // ── Save / Create Job ─────────────────────────────────────────
  async function handleSaveJob() {
    setError(null);
    setSaving(true);
    try {
      let job: JobDetail;
      if (savedJob) {
        job = await updateJob(savedJob.id, { title, description, folder_link: folderLink, company: company || undefined });
      } else {
        job = await createJob({ title, description, folder_link: folderLink, company: company || undefined });
      }
      setSavedJob(job);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  // ── Check Folder ──────────────────────────────────────────────
  async function handleCheckFolder() {
    if (!savedJob) return;
    setCheckingFolder(true);
    setFolderResult(null);
    try {
      const result = await checkFolder(savedJob.id);
      setFolderResult(result);
    } catch (e) {
      setFolderResult({ success: false, folder_name: null, pdf_count: null, error: e instanceof Error ? e.message : "Check failed" });
    } finally {
      setCheckingFolder(false);
    }
  }

  // ── Save Skills ───────────────────────────────────────────────
  async function handleSaveSkills() {
    if (!savedJob) return;
    setSavingSkills(true);
    setError(null);
    try {
      const validSkills = skills.filter((s) => s.skill.trim().length > 0);
      await setSkills(savedJob.id, validSkills);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save skills");
    } finally {
      setSavingSkills(false);
    }
  }

  // ── Skill list management ─────────────────────────────────────
  function updateSkill(index: number, field: string, value: unknown) {
    setSkillsList((prev) =>
      prev.map((s, i) => (i === index ? { ...s, [field]: value } : s))
    );
  }

  function removeSkill(index: number) {
    setSkillsList((prev) => prev.filter((_, i) => i !== index));
  }

  function addSkill() {
    setSkillsList((prev) => [...prev, emptySkill()]);
  }

  // ── Copy email helper ─────────────────────────────────────────
  function copyEmail() {
    navigator.clipboard.writeText(saEmail).then(() => {
      setCopiedEmail(true);
      setTimeout(() => setCopiedEmail(false), 2000);
    });
  }

  const isDraft = !savedJob || savedJob.status === "draft";

  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif", maxWidth: 800, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "2rem" }}>
        <button onClick={onBack} style={linkBtnStyle}>← Back</button>
        <h1 style={{ margin: 0 }}>{savedJob ? "Edit JD" : "New JD"}</h1>
      </div>

      {error && <p style={{ color: "#c00", marginBottom: "1rem" }}>{error}</p>}

      {/* ── Job Details Section ─────────────────────────────────── */}
      <section style={sectionStyle}>
        <h2 style={sectionTitle}>Job Details</h2>

        <label style={labelStyle}>
          Job Title *
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={inputStyle} placeholder="e.g. Data Engineer" disabled={!isDraft} />
        </label>

        <label style={labelStyle}>
          Job Description *
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} style={{ ...inputStyle, minHeight: 120, resize: "vertical" }} placeholder="Describe the role requirements…" disabled={!isDraft} />
        </label>

        <label style={labelStyle}>
          Company / Team
          <input value={company} onChange={(e) => setCompany(e.target.value)} style={inputStyle} placeholder="Optional" disabled={!isDraft} />
        </label>

        <label style={labelStyle}>
          Google Drive Folder Link *
          <input value={folderLink} onChange={(e) => setFolderLink(e.target.value)} style={inputStyle} placeholder="https://drive.google.com/drive/folders/..." disabled={!isDraft} />
        </label>

        {isDraft && (
          <button onClick={handleSaveJob} disabled={saving || !title || !description || !folderLink} style={primaryBtnStyle}>
            {saving ? "Saving…" : savedJob ? "Update Job" : "Create Job"}
          </button>
        )}
      </section>

      {/* ── Folder Connection Section ──────────────────────────── */}
      {savedJob && (
        <section style={sectionStyle}>
          <h2 style={sectionTitle}>Connect Drive Folder</h2>

          {saEmail && (
            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem", color: "#475569" }}>
                Share your recruitment folder with this service account as <strong>Viewer</strong>:
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <code style={{ flex: 1, background: "#fff", padding: "0.5rem", borderRadius: 4, border: "1px solid #e2e8f0", fontSize: "0.875rem" }}>{saEmail}</code>
                <button onClick={copyEmail} style={secondaryBtnStyle}>
                  {copiedEmail ? "Copied ✓" : "Copy"}
                </button>
              </div>
            </div>
          )}

          <button onClick={handleCheckFolder} disabled={checkingFolder} style={secondaryBtnStyle}>
            {checkingFolder ? "Checking…" : "Check folder access"}
          </button>

          {folderResult && (
            <div style={{
              marginTop: "1rem",
              padding: "1rem",
              borderRadius: 8,
              background: folderResult.success ? "#f0fdf4" : "#fef2f2",
              border: `1px solid ${folderResult.success ? "#bbf7d0" : "#fecaca"}`,
            }}>
              {folderResult.success ? (
                <>
                  <p style={{ margin: 0, color: "#15803d" }}>
                    ✓ <strong>{folderResult.folder_name}</strong> — {folderResult.pdf_count} PDF{folderResult.pdf_count !== 1 ? "s" : ""} found
                  </p>
                </>
              ) : (
                <p style={{ margin: 0, color: "#b91c1c" }}>✗ {folderResult.error}</p>
              )}
            </div>
          )}
        </section>
      )}

      {/* ── Skills Section ─────────────────────────────────────── */}
      {savedJob && (
        <section style={sectionStyle}>
          <h2 style={sectionTitle}>Skills & Requirements</h2>

          {skills.map((skill, i) => (
            <div key={i} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
              <div style={{ display: "flex", gap: "0.75rem", marginBottom: "0.75rem" }}>
                <label style={{ ...labelStyle, flex: 1 }}>
                  Skill *
                  <input value={skill.skill} onChange={(e) => updateSkill(i, "skill", e.target.value)} style={inputStyle} placeholder="e.g. Python" disabled={!isDraft} />
                </label>
                {isDraft && (
                  <button onClick={() => removeSkill(i)} style={{ ...linkBtnStyle, color: "#b91c1c", alignSelf: "flex-end", marginBottom: 4 }}>
                    Remove
                  </button>
                )}
              </div>

              <label style={labelStyle}>
                Requirement Description
                <input value={skill.description ?? ""} onChange={(e) => updateSkill(i, "description", e.target.value)} style={inputStyle} placeholder="Describe the intended application…" disabled={!isDraft} />
              </label>

              <div style={{ display: "flex", gap: "1.5rem", alignItems: "center", marginTop: "0.75rem", flexWrap: "wrap" }}>
                {/* Mandatory checkbox */}
                <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
                  <input type="checkbox" checked={skill.mandatory} onChange={(e) => updateSkill(i, "mandatory", e.target.checked)} disabled={!isDraft} />
                  Mandatory
                </label>

                {/* Assessment method */}
                <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  Method:
                  <select value={skill.assessment_method} onChange={(e) => updateSkill(i, "assessment_method", e.target.value)} disabled={!isDraft} style={selectStyle}>
                    <option value="resume">Resume</option>
                    <option value="interview">Interview</option>
                  </select>
                </label>
              </div>

              {/* Only show sliders for resume-assessed skills */}
              {skill.assessment_method === "resume" && (
                <div style={{ display: "flex", gap: "2rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
                  {/* Importance slider */}
                  <label style={{ flex: 1, minWidth: 200 }}>
                    <span style={{ fontSize: "0.85rem" }}>Importance: <strong>{skill.importance}</strong> — {IMPORTANCE_LABELS[skill.importance]}</span>
                    <input type="range" min={1} max={5} value={skill.importance} onChange={(e) => updateSkill(i, "importance", Number(e.target.value))} disabled={!isDraft} style={{ width: "100%" }} />
                  </label>

                  {/* Evidence level slider */}
                  <label style={{ flex: 1, minWidth: 200 }}>
                    <span style={{ fontSize: "0.85rem" }}>Required Evidence: <strong>{skill.required_evidence_level}</strong> — {EVIDENCE_LABELS[skill.required_evidence_level]}</span>
                    <input type="range" min={1} max={5} value={skill.required_evidence_level} onChange={(e) => updateSkill(i, "required_evidence_level", Number(e.target.value))} disabled={!isDraft} style={{ width: "100%" }} />
                  </label>
                </div>
              )}

              {/* Aliases */}
              <label style={{ ...labelStyle, marginTop: "0.75rem" }}>
                <span style={{ fontSize: "0.85rem" }}>Aliases (comma-separated)</span>
                <input
                  value={(skill.aliases ?? []).join(", ") || ""}
                  onChange={(e) => updateSkill(i, "aliases", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                  style={inputStyle}
                  placeholder="e.g. Python3, Py"
                  disabled={!isDraft}
                />
              </label>
            </div>
          ))}

          {isDraft && (
            <div style={{ display: "flex", gap: "1rem" }}>
              <button onClick={addSkill} style={secondaryBtnStyle}>+ Add Skill</button>
              <button onClick={handleSaveSkills} disabled={savingSkills} style={primaryBtnStyle}>
                {savingSkills ? "Saving…" : "Save Skills"}
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────

const sectionStyle: React.CSSProperties = {
  marginBottom: "2rem",
  padding: "1.5rem",
  border: "1px solid #e5e7eb",
  borderRadius: 12,
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 1rem",
  fontSize: "1.1rem",
};

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.3rem",
  marginBottom: "0.75rem",
  fontSize: "0.9rem",
  fontWeight: 500,
  color: "#374151",
};

const inputStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  fontSize: "0.9rem",
  fontFamily: "inherit",
};

const selectStyle: React.CSSProperties = {
  padding: "0.3rem 0.5rem",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  fontSize: "0.85rem",
};

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

const secondaryBtnStyle: React.CSSProperties = {
  padding: "0.5rem 1rem",
  background: "#fff",
  color: "#374151",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.875rem",
};

const linkBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#2563eb",
  cursor: "pointer",
  fontSize: "0.9rem",
};
