import { useEffect, useRef, useState } from "react";
import { deleteJob, type JobSummary } from "../services/jobs";

interface Props {
  job: JobSummary;
  onCancel: () => void;
  onDeleted: () => void;
}

export default function DeleteJobDialog({ job, onCancel, onDeleted }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    cancel.current?.focus();
    return () => element.close();
  }, []);

  async function confirm() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      await deleteJob(job.id);
      dialog.current?.close();
      onDeleted();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not delete the job. Please try again.");
      pending.current = false;
      setBusy(false);
    }
  }

  function dismiss() {
    if (pending.current) return;
    dialog.current?.close();
    onCancel();
  }

  return <dialog ref={dialog} className="jobs-delete-dialog" aria-labelledby="delete-job-title" aria-describedby="delete-job-description"
    onCancel={(event) => { event.preventDefault(); dismiss(); }}
    onKeyDown={(event) => {
      if (event.key !== "Tab") return;
      if (event.shiftKey && document.activeElement === cancel.current) {
        event.preventDefault(); confirmButton.current?.focus();
      } else if (!event.shiftKey && document.activeElement === confirmButton.current) {
        event.preventDefault(); cancel.current?.focus();
      }
    }}>
    <h2 id="delete-job-title">Delete this job?</h2>
    <p className="jobs-delete-name">{job.title}</p>
    <p id="delete-job-description">Permanently delete this job, its requirements, and all saved assessments and results. This cannot be undone. Original files in Google Drive will stay unchanged.</p>
    {error && <p role="alert" className="jobs-error">{error}</p>}
    <div className="jobs-dialog-actions">
      <button ref={cancel} type="button" className="jobs-cancel" aria-disabled={busy} onClick={dismiss}>Cancel</button>
      <button ref={confirmButton} type="button" className="jobs-delete" aria-disabled={busy} aria-busy={busy} onClick={confirm}>{busy ? "Deleting…" : "Delete job"}</button>
    </div>
  </dialog>;
}
