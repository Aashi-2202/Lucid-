import { useEffect, useRef, useState } from "react";
import type { JobDetail } from "../services/jobs";
import { checkFolder } from "../services/jobs";
import { getEngine, listRuns, startRun } from "../services/assessments";
import type { RunProgress } from "../services/assessments";

interface Props {job:JobDetail;dirty:boolean;onStarted:(id:string)=>void}
export default function AssessmentLaunch({job,dirty,onStarted}:Props) {
  const [runs,setRuns]=useState<RunProgress[]>([]);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  useEffect(()=>{let cancelled=false;listRuns(job.id).then(value=>{if(!cancelled)setRuns(value)}).catch(()=>{if(!cancelled)setError("Previous assessments could not load. Reopen this job to retry.")});return()=>{cancelled=true}},[job.id]);
  async function initiate() {
    if(lock.current)return;
    if(dirty){setError("Save your changes before starting the assessment.");return}
    if(!job.skills.length){setError("Add and save at least one skill before starting.");return}
    lock.current=true;setBusy(true);setError("");
    try {
      const engine=await getEngine();
      if(!engine.ready)throw new Error(engine.message);
      const folder=await checkFolder(job.id);
      if(!folder.success)throw new Error(folder.error || "Folder access could not be verified.");
      if(!folder.pdf_count)throw new Error("No PDFs were found directly inside this folder.");
      const storageKey=`lucid-start-${job.id}`;
      let key=localStorage.getItem(storageKey);
      if(!key){key=crypto.randomUUID();localStorage.setItem(storageKey,key)}
      const run=await startRun(job.id,key);
      localStorage.removeItem(storageKey);
      onStarted(run.id);
    }catch(err){setError(err instanceof Error?err.message:"Could not start. Your saved configuration is unchanged.")}
    finally{lock.current=false;setBusy(false)}
  }
  return <section className="setup-section" aria-labelledby="assessment-title">
    <h2 id="assessment-title">Review and assess</h2>
    <p className="setup-help">{job.folder_name || "Your saved Drive folder"}{job.folder_pdf_count!=null?` · ${job.folder_pdf_count} PDFs at last check`:""}</p>
    <ul className="assessment-requirements">{job.skills.map((skill,index)=><li key={skill.id??index}><strong>{skill.skill}</strong>{skill.mandatory?" · Mandatory":" · Optional"}{skill.assessment_method==="interview"?" · Interview, unscored":` · Weight ${skill.importance}/5 · Evidence ${skill.required_evidence_level}/5`}</li>)}</ul>
    <p className="setup-help">Processes one PDF at a time. Missing mandatory requirements are excluded before analysis. Original files stay unchanged.</p>
    {dirty&&<p className="setup-help">Your unsaved changes are not included in this summary.</p>}
    {error&&<p role="alert" className="setup-error">{error}</p>}
    <button type="button" className="setup-primary" onClick={initiate} disabled={busy} aria-busy={busy}>Initiate assessment</button>
    {busy&&<p role="status">Checking readiness and folder access…</p>}
    {runs.length>0&&<div className="assessment-history"><h3>Previous assessments</h3>{runs.map(run=><button type="button" key={run.id} className="setup-secondary" onClick={()=>onStarted(run.id)}>{new Date(run.created_at).toLocaleString()} · {run.status} · {run.processed_files}/{run.total_files??"?"} processed</button>)}</div>}
  </section>;
}
