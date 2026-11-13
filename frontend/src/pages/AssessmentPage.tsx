import { useEffect, useRef, useState } from "react";
import { downloadResults, getFile, getFiles, getResults, getRun, getSnapshot } from "../services/assessments";
import type { FileDetail, FileOutcome, RankedResume, RunProgress, RunSnapshot } from "../services/assessments";
import "./JobSetupPage.css";
import "./AssessmentPage.css";

interface Props {assessmentId:string;onBack:()=>void}
const active=(run:RunProgress)=>run.status==="queued"||run.status==="running";
const LEVELS=["", "Mention / basic", "Coursework / program", "Applied project", "Internship", "Relevant work ≥ 6 months"];

export default function AssessmentPage({assessmentId,onBack}:Props) {
  const [run,setRun]=useState<RunProgress|null>(null);
  const [snapshot,setSnapshot]=useState<RunSnapshot|null>(null);
  const [snapshotError,setSnapshotError]=useState(false);
  const [files,setFiles]=useState<FileOutcome[]>([]);
  const [results,setResults]=useState<RankedResume[]>([]);
  const [provisional,setProvisional]=useState(false);
  const [error,setError]=useState("");
  const [attempt,setAttempt]=useState(0);
  const [updated,setUpdated]=useState("");
  const [paused,setPaused]=useState(false);
  const [view,setView]=useState("ranked");
  const [detail,setDetail]=useState<FileDetail|null>(null);
  const [detailBusy,setDetailBusy]=useState(false);
  const [detailError,setDetailError]=useState("");
  const [exporting,setExporting]=useState(false);
  const detailRequest=useRef(0);
  const detailHeading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>()=>{detailRequest.current++},[assessmentId]);
  useEffect(()=>{if(detailBusy||detail||detailError){detailHeading.current?.focus({preventScroll:true});detailHeading.current?.scrollIntoView({block:"start"})}},[detailBusy,detail,detailError]);
  useEffect(()=>{
    let cancelled=false;let timer:ReturnType<typeof setTimeout>|undefined;let failures=0;
    getSnapshot(assessmentId).then(value=>{if(!cancelled){setSnapshot(value);setSnapshotError(false)}}).catch(()=>{if(!cancelled)setSnapshotError(true)});
    setPaused(false);
    async function refresh() {
      try {
        const [next,outcomes,ranked]=await Promise.all([getRun(assessmentId),getFiles(assessmentId),getResults(assessmentId)]);
        if(cancelled)return;
        setRun(next);setFiles(outcomes);setResults(ranked.rows);setProvisional(ranked.provisional);setError("");setUpdated(new Date().toLocaleTimeString());failures=0;
        if(active(next))timer=setTimeout(refresh,2500);
      }catch(err){
        if(cancelled)return;
        setError(err instanceof Error?err.message:"Could not refresh assessment.");
        failures++;
        if(failures<3)timer=setTimeout(refresh,5000);else setPaused(true);
      }
    }
    void refresh();
    return()=>{cancelled=true;if(timer)clearTimeout(timer)};
  },[assessmentId,attempt]);
  async function inspect(id:number) {
    const request=++detailRequest.current;
    setDetailBusy(true);setDetailError("");setDetail(null);
    try{const value=await getFile(assessmentId,id);if(request===detailRequest.current)setDetail(value)}catch(err){if(request===detailRequest.current)setDetailError(err instanceof Error?err.message:"Could not load resume details.")}
    finally{if(request===detailRequest.current)setDetailBusy(false)}
  }
  async function exportCsv(){setExporting(true);try{await downloadResults(assessmentId)}catch(err){setError(err instanceof Error?err.message:"Export failed.")}finally{setExporting(false)}}
  const selected=files.filter(file=>view==="excluded"?file.status==="excluded":view==="failed"?file.status==="failed":file.status==="ready_for_analysis");
  const busy=run?active(run):true;
  return <main className="job-setup assessment-page">
    <header className="setup-heading"><button className="setup-link" onClick={onBack}>← Job setup</button><h1>Assessment</h1></header>
    <p className="assessment-job-title">{snapshot?.title || "Resume assessment"}</p>
    {snapshotError&&<p className="setup-error" role="alert">The saved requirement summary could not load. <button className="setup-link" onClick={()=>setAttempt(value=>value+1)}>Retry updates</button></p>}
    {error&&<div role="alert" className="setup-error"><p>{error}</p>{paused&&<p>{run?"Updates paused. Last saved progress is shown.":"Updates paused. Retry to load the saved assessment."}</p>}<button className="setup-secondary" onClick={()=>setAttempt(value=>value+1)}>Retry updates</button></div>}
    {!run&&!error&&<p role="status">Loading assessment…</p>}
    {run&&<>
      <section className="setup-section" aria-labelledby="progress-title">
        <h2 id="progress-title">{run.status==="completed"?"Assessment complete":run.status==="failed"?"Assessment stopped":run.status==="screened"?"Intake complete":run.phase==="discovery"?"Discovering resumes":"Screening and analysing resumes"}</h2>
        <p role="status" aria-live="polite">{run.total_files==null?"Reading the folder’s PDF list…":`${run.processed_files} of ${run.total_files} processed`}</p>
        <progress max={run.total_files||1} {...(run.total_files==null?{}:{value:run.processed_files})} aria-label="Assessment progress" />
        <dl className="assessment-counts"><div><dt>Assessed</dt><dd>{run.assessed}</dd></div><div><dt>Excluded</dt><dd>{run.excluded}</dd></div><div><dt>Failed</dt><dd>{run.failed}</dd></div></dl>
        {run.current_file_name&&<p className="setup-help">Current resume: {run.current_file_name}</p>}
        {run.error_message&&<p role="alert" className="setup-error">{run.error_message}</p>}
        {run.status==="screened"&&<p className="setup-help">This older run contains intake only. Start a new assessment from job setup for evidence analysis and ranking.</p>}
        <p className="setup-help">{updated?`Last updated ${updated}. `:""}{busy?"You can leave this page and reopen the saved assessment.":"Results are saved."}</p>
      </section>
      <section className="setup-section" aria-labelledby="results-title">
        <div className="assessment-result-heading"><h2 id="results-title">{busy||provisional?"Provisional results":"Results"}</h2><button className="setup-secondary" onClick={exportCsv} disabled={busy||exporting||results.length===0} aria-busy={exporting}>Download results</button></div>
        <p className="setup-help">Automated scores describe resume evidence. Review the supporting passages before using results. Equal scores share a rank.</p>
        {snapshot?.analysis_version==="resume-evidence-v2"&&<p className="setup-help">Scores reflect how well the resume evidence meets each requirement, using the importance you set. Similarity only helps find evidence.</p>}
        {snapshot?.analysis_version==="resume-evidence-v1"&&<p className="setup-help">This saved assessment uses the older similarity-weighted scoring policy. Start a new assessment to use evidence-fulfilment scoring.</p>}
        {!busy&&provisional&&<p className="setup-help">Some evidence is undetermined. Scores remain provisional; review resumes marked Needs review.</p>}
        <p className="setup-help">Download results as a spreadsheet-compatible CSV file.</p>
        {snapshot?.summary_version==="job-match-summary-v1"?<p className="setup-help">The CSV includes a Job Match Summary of technical alignment and any additional competencies you chose. Additional competencies are unscored.</p>:snapshot&&<p className="setup-help">Job Match Summary is unavailable for this saved assessment. Start a new assessment to include it.</p>}
        {snapshot?.skills.every(skill=>skill.assessment_method==="interview")&&<p className="setup-help">All requirements are interview-assessed. Passing resumes have no numerical score or rank.</p>}
        <div className="assessment-filters" role="group" aria-label="Result categories">
          <button className="setup-secondary" aria-pressed={view==="ranked"} onClick={()=>setView("ranked")}>Assessed ({results.length})</button>
          <button className="setup-secondary" aria-pressed={view==="excluded"} onClick={()=>setView("excluded")}>Excluded ({run.excluded})</button>
          <button className="setup-secondary" aria-pressed={view==="failed"} onClick={()=>setView("failed")}>Failed ({run.failed})</button>
        </div>
        {view==="ranked"?(results.length===0?<p className="setup-help">{busy?"Assessed resumes will appear as processing continues.":"No assessed resumes. Review exclusions and processing failures."}</p>:<div className="assessment-table-scroll"><table><caption className="sr-only">Resume assessment results</caption><thead><tr><th scope="col">Rank</th><th scope="col">Resume</th><th scope="col">Match score</th><th scope="col">Assessment</th></tr></thead><tbody>{results.map(row=><tr key={row.file_id}><td>{row.rank??"—"}</td><th scope="row"><button className="setup-link" onClick={()=>inspect(row.file_id)}>{row.name}</button></th><td>{row.score==null?"Unscored":`${row.score.toFixed(2)} / 100`}</td><td>{row.complete?"Complete":"Needs review"}</td></tr>)}</tbody></table></div>):(selected.length===0?<p className="setup-help">No {view} resumes.</p>:<ul className="assessment-outcomes">{selected.map(file=><li key={file.id}><strong>{file.name}</strong><p>{view==="excluded"?`Missing mandatory: ${file.missing_skills.join(", ")}`:file.error_message}</p></li>)}</ul>)}
      </section>
      <section className="setup-section" aria-labelledby="resume-review-title">
        <h2 id="resume-review-title" ref={detailHeading} tabIndex={-1}>Resume details</h2>
        {!detail&&!detailBusy&&!detailError&&<p className="setup-help">Select a resume in the results to view its extracted information and supporting passages.</p>}
        {detailBusy&&<p role="status">Loading resume details…</p>}
        {detailError&&<p role="alert" className="setup-error">{detailError}</p>}
        {detail?.document?.analysis&&<><h3 className="assessment-resume-name">{detail.name}</h3><p className="setup-help">Explicitly found requirements: {detail.document.analysis.extracted_skills.join(", ")||"None"}</p>
          {detail.document.analysis.job_match_summary&&<div className="assessment-match-summary"><h3>Job Match Summary</h3><p>{detail.document.analysis.job_match_summary}</p></div>}
          {!!detail.document.analysis.additional_competencies?.length&&<div className="assessment-match-summary"><h3>Additional competencies · Unscored</h3><p className="setup-help">Resume mentions and activities are supporting signals, not verified ability.</p><ul>{detail.document.analysis.additional_competencies.map(item=><li key={item.name}><strong>{item.name}</strong> — {item.reason}{item.pages.length?` (Page ${item.pages.join(", ")})`:""}</li>)}</ul></div>}
          {detail.document.analysis.skills.map((skill,index)=><details className="assessment-skill-detail" key={index}><summary>{skill.skill} · {skill.assessment_method==="interview"?"Interview, unscored":skill.evidence_level?`Evidence ${skill.evidence_level}/5 — ${LEVELS[skill.evidence_level]}`:skill.match_type==="absent"?"Not found":"Undetermined"}</summary><p>{skill.reason}</p><p className="setup-help">Match: {skill.match_type==="semantic"?"semantic association":skill.match_type==="explicit"?"explicit name or approved alias":"not found"}</p>{skill.assessment_method==="resume"&&<p className="setup-help">Required evidence {skill.required_evidence_level}/5 · Importance {skill.importance}/5 · {detail.document?.analysis?.version==="resume-evidence-v2"?`Requirement credit ${(skill.evidence_credit*100).toFixed(1)}%`:`Relevance credit ${skill.relevance}`} · Skill credit {skill.skill_credit.toFixed(3)}</p>}{skill.evidence.map((source,i)=><blockquote key={i}><p>{source.text}</p><footer>Page {source.page} · {source.section}{source.context?` · ${source.context}`:""}</footer></blockquote>)}</details>)}
          {Object.entries(detail.document.analysis.sections).filter(([,entries])=>entries.length).map(([section,entries])=><details className="assessment-skill-detail" key={section}><summary>Extracted {section}</summary>{entries.map((source,index)=><p key={index}>{source.text} <small>(page {source.page})</small></p>)}</details>)}
          <details className="assessment-skill-detail"><summary>Extracted PDF text</summary>{detail.document.blocks.map((block,index)=><p key={index} className="assessment-source-text">Page {block.page}: {block.original_text}</p>)}</details>
        </>}
      </section>
    </>}
  </main>;
}
