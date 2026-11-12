import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { createJob, getJob, updateJob, checkFolder, getServiceAccountEmail } from "../services/jobs";
import type { JobDetail, FolderCheckResult } from "../services/jobs";
import { newSkillDraft, skillInputs } from "../services/skillDrafts";
import type { SkillDraft } from "../services/skillDrafts";
import { useAuth } from "../components/AuthProvider";
import SkillsEditor from "../components/SkillsEditor";
import AssessmentLaunch from "../components/AssessmentLaunch";
import "./AssessmentPage.css";
import "./JobSetupPage.css";

interface Props { jobId?: number; onBack: () => void; onAssessment:(id:string,jobId:number)=>void }

export default function JobSetupPage({ jobId, onBack, onAssessment }: Props) {
  const { recruiter } = useAuth();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [folderLink, setFolderLink] = useState("");
  const [company, setCompany] = useState("");
  const [savedJob, setSavedJob] = useState<JobDetail | null>(null);
  const [skills, setSkills] = useState<SkillDraft[]>(() => [newSkillDraft()]);
  const [folderResult, setFolderResult] = useState<FolderCheckResult | null>(null);
  const [checkingFolder, setCheckingFolder] = useState(false);
  const [saEmail, setSaEmail] = useState("");
  const [copiedEmail, setCopiedEmail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(Boolean(jobId));
  const [loadError, setLoadError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  const savingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    if (jobId) {
      setLoading(true);
      setLoadError(false);
      getJob(jobId).then(job => {
        if (cancelled) return;
        setSavedJob(job); setTitle(job.title); setDescription(job.description);
        setFolderLink(job.folder_link); setCompany(job.company ?? "");
        setSkills(job.skills.map(newSkillDraft));
        if (job.folder_name) setFolderResult({success:true, folder_name:job.folder_name, pdf_count:job.folder_pdf_count, error:null});
        setError(null); setDirty(false);
      }).catch((err: unknown) => {
        if (!cancelled) { setLoadError(true); setError(err instanceof Error ? err.message : "Could not load the job. Please try again."); }
      }).finally(() => { if (!cancelled) setLoading(false); });
    }
    getServiceAccountEmail().then(result => { if (!cancelled) setSaEmail(result.email); }).catch(() => {});
    return () => { cancelled = true; };
  }, [jobId, loadAttempt]);

  useEffect(() => {
    function warn(event: BeforeUnloadEvent) { if (dirty) event.preventDefault(); }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function changed() { setDirty(true); setMessage(""); }
  function goBack() { if (!dirty || window.confirm("Leave without saving your changes?")) onBack(); }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingRef.current) return;
    savingRef.current = true; setSaving(true); setError(null); setMessage("");
    try {
      const input = { title:title.trim(), description:description.trim(), folder_link:folderLink.trim(), company:company.trim() || null, skills:skillInputs(skills) };
      if (!input.title || !input.description || !input.folder_link) throw new Error("Enter a job title, description, and Drive folder link.");
      const job = savedJob ? await updateJob(savedJob.id, input) : await createJob(input);
      const folderChanged = savedJob?.folder_link !== job.folder_link;
      setSavedJob(job); setTitle(job.title); setDescription(job.description); setCompany(job.company ?? ""); setFolderLink(job.folder_link);
      // Preserve stable row keys and open matching settings after saving.
      setDirty(false); setMessage("Job details and skill requirements saved.");
      if (folderChanged) setFolderResult(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save the job. Your changes are still here."); }
    finally { savingRef.current = false; setSaving(false); }
  }

  async function checkAccess() {
    if (!savedJob) return;
    setCheckingFolder(true); setFolderResult(null);
    try { setFolderResult(await checkFolder(savedJob.id)); }
    catch (err) { setFolderResult({success:false, folder_name:null, pdf_count:null, error:err instanceof Error ? err.message : "Folder check failed. Please try again."}); }
    finally { setCheckingFolder(false); }
  }

  async function copyEmail() {
    try { await navigator.clipboard.writeText(saEmail); setCopiedEmail(true); }
    catch { setError("Could not copy the email. Select and copy the displayed address."); }
  }

  const isDraft = !savedJob || savedJob.status === "draft";
  const disabled = !isDraft || saving;
  const folderEdited = Boolean(savedJob && savedJob.folder_link !== folderLink.trim());

  return (
    <main className="job-setup">
      <header className="setup-heading">
        <button type="button" onClick={goBack} className="setup-link" disabled={saving}>← Back</button>
        <h1>{savedJob || jobId ? "Edit JD" : "New JD"}</h1>
      </header>
      {error && <p role="alert" className="setup-error">{error}</p>}
      {loading && <p role="status">Loading job configuration…</p>}
      {loadError && <button type="button" className="setup-secondary" onClick={() => setLoadAttempt(value => value + 1)}>Try again</button>}
      {!loading && !loadError && <>
        {!isDraft && <p className="setup-help">This job is read-only. Only draft jobs can be edited.</p>}
        <form onSubmit={save} onChange={changed}>
          <section className="setup-section" aria-labelledby="job-details-title">
            <h2 id="job-details-title">Job Details</h2>
            <fieldset className="setup-fields" disabled={disabled}>
              <label className="setup-field">Job Title *
                <input value={title} onChange={event => setTitle(event.target.value)} required maxLength={255} placeholder="e.g. Data Engineer" />
              </label>
              <label className="setup-field">Job Description *
                <textarea value={description} onChange={event => setDescription(event.target.value)} required rows={6} placeholder="Describe the role requirements…" />
              </label>
              <label className="setup-field">Company / Team
                <input value={company} onChange={event => setCompany(event.target.value)} placeholder="Optional" />
              </label>
              <label className="setup-field">Google Drive Folder Link *
                <input value={folderLink} onChange={event => {setFolderLink(event.target.value); setFolderResult(null);}}
                  required placeholder="https://drive.google.com/drive/folders/..." />
              </label>
              <p className="setup-help">Recruiter: {recruiter?.email ?? recruiter?.username ?? recruiter?.name}</p>
            </fieldset>
          </section>
          <SkillsEditor skills={skills} onChange={value => {setSkills(value); changed();}} disabled={disabled} />
          {isDraft && <div className="setup-actions">
            <button type="submit" disabled={saving} aria-busy={saving} className="setup-primary">{savedJob ? "Save changes" : "Create Job"}</button>
            <span role="status">{saving ? "Saving…" : message || (dirty ? "Unsaved changes" : "")}</span>
          </div>}
        </form>
        {savedJob && <section className="setup-section" aria-labelledby="folder-title">
          <h2 id="folder-title">Connect Drive Folder</h2>
          {saEmail && <div className="folder-sharing">
            <p>Share your recruitment folder with this service account as <strong>Viewer</strong>:</p>
            <div className="folder-email"><code>{saEmail}</code><button type="button" onClick={copyEmail} className="setup-secondary">Copy email</button></div>
            {copiedEmail && <p role="status">Email copied.</p>}
          </div>}
          {!saEmail && <p className="setup-help">The service-account email is unavailable. Contact the administrator if folder access fails.</p>}
          {folderEdited && <p className="setup-help">Save your updated folder link before checking access.</p>}
          <button type="button" onClick={checkAccess} disabled={checkingFolder || saving || folderEdited} aria-busy={checkingFolder} className="setup-secondary">Check folder access</button>
          {checkingFolder && <p role="status">Checking folder access…</p>}
          {folderResult && <div role={folderResult.success ? "status" : "alert"} className={`folder-result ${folderResult.success ? "folder-success" : "folder-error"}`}>
            {folderResult.success ? <p><strong>{folderResult.folder_name}</strong> — {folderResult.pdf_count} PDF{folderResult.pdf_count !== 1 ? "s" : ""} found</p> : <p>{folderResult.error}</p>}
          </div>}
        </section>}
        {savedJob&&<AssessmentLaunch job={savedJob} dirty={dirty} onStarted={id=>onAssessment(id,savedJob.id)} />}
      </>}
    </main>
  );
}
