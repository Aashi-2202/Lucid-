import { apiFetch, API_BASE } from "./api";
import { getToken } from "./auth";
import { resultsFilename } from "./exportFilename";

export interface RunProgress {
  id:string; job_id:number; status:"queued"|"running"|"screened"|"completed"|"failed";
  phase:string; total_files:number|null; processed_files:number; ready_for_analysis:number;
  assessed:number; excluded:number; failed:number; current_file_name:string|null;
  error_code:string|null; error_message:string|null; created_at:string; finished_at:string|null;
}
export interface FileOutcome {id:number;name:string;status:string;missing_skills:string[];error_code:string|null;error_message:string|null}
export interface RankedResume {file_id:number;name:string;rank:number|null;score:number|null;complete:boolean;job_match_summary?:string|null}
export interface CompetencyFinding {name:string;status:"supporting_activity"|"listed"|"not_evidenced";reason:string;pages:number[]}
export interface Evidence {page:number;block:number;section:string;text:string;context:string}
export interface SkillResult {skill:string;assessment_method:string;mandatory:boolean;importance:number;required_evidence_level:number|null;evidence_level:number|null;relevance:number;evidence_credit:number;skill_credit:number;match_type:string;reason:string;evidence:Evidence[]}
export interface FileDetail extends FileOutcome {document:{page_count:number;blocks:{page:number;original_text:string}[];analysis:{version?:string;score:number|null;complete:boolean;skills:SkillResult[];sections:Record<string,Evidence[]>;extracted_skills:string[];job_match_summary?:string|null;additional_competencies?:CompetencyFinding[]}|null}|null}
export interface RunSnapshot {title:string;skills:{skill:string;mandatory:boolean;importance:number;required_evidence_level:number;assessment_method:string}[];folder_link:string;analysis_version:string|null;summary_version?:string|null;additional_competencies?:string[]}

export const getEngine = () => apiFetch<{ready:boolean;message:string}>("/assessment-engine");
export const listRuns = (jobId:number) => apiFetch<RunProgress[]>(`/jobs/${jobId}/assessments`);
export const startRun = (jobId:number,key:string) => apiFetch<RunProgress>(`/jobs/${jobId}/assessments`,{method:"POST",body:JSON.stringify({idempotency_key:key})});
export const getRun = (id:string) => apiFetch<RunProgress>(`/assessments/${id}`);
export const getSnapshot = (id:string) => apiFetch<RunSnapshot>(`/assessments/${id}/snapshot`);
export const getResults = (id:string) => apiFetch<{provisional:boolean;rows:RankedResume[]}>(`/assessments/${id}/results`);
export const getFile = (id:string,fileId:number) => apiFetch<FileDetail>(`/assessments/${id}/files/${fileId}`);
export async function getFiles(id:string):Promise<FileOutcome[]> {
  const files:FileOutcome[]=[];
  for (let offset=0;offset<1000;offset+=200) {
    const page=await apiFetch<FileOutcome[]>(`/assessments/${id}/files?limit=200&offset=${offset}`);
    files.push(...page);
    if (page.length<200) break;
  }
  return files;
}
export async function downloadResults(id:string,jobTitle?:string) {
  const filename=resultsFilename(jobTitle ?? (await getSnapshot(id)).title);
  const response=await fetch(`${API_BASE}/assessments/${id}/export`,{signal:AbortSignal.timeout(30000),headers:{Authorization:`Bearer ${getToken()}`}});
  if (!response.ok) throw new Error("Could not export results. Please try again after the assessment finishes.");
  const url=URL.createObjectURL(await response.blob());
  const link=document.createElement("a"); link.href=url;link.download=filename;link.click();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}
