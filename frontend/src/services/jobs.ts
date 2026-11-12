import { apiFetch } from "./api";
import type {
  SkillRequirement,
} from "../types";

// ── Types ─────────────────────────────────────────────────────────

export interface JobSummary {
  id: number;
  title: string;
  company: string | null;
  status: string;
  folder_pdf_count: number | null;
}

export interface JobDetail {
  id: number;
  title: string;
  description: string;
  folder_link: string;
  folder_id: string;
  folder_name: string | null;
  folder_pdf_count: number | null;
  company: string | null;
  recruiter_email: string;
  status: string;
  skills: SkillRequirement[];
}

export interface CreateJobInput {
  title: string;
  description: string;
  folder_link: string;
  company?: string | null;
  skills?: Omit<SkillRequirement, "id">[];
}

export interface FolderCheckResult {
  success: boolean;
  folder_name: string | null;
  pdf_count: number | null;
  error: string | null;
}

// ── API calls ─────────────────────────────────────────────────────

export function listJobs(): Promise<JobSummary[]> {
  return apiFetch<JobSummary[]>("/jobs");
}

export function getJob(id: number): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/jobs/${id}`);
}

export function deleteJob(id: number): Promise<void> {
  return apiFetch<void>(`/jobs/${id}`, { method: "DELETE" });
}

export function createJob(input: CreateJobInput): Promise<JobDetail> {
  return apiFetch<JobDetail>("/jobs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateJob(
  id: number,
  input: Partial<CreateJobInput>
): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function checkFolder(jobId: number): Promise<FolderCheckResult> {
  return apiFetch<FolderCheckResult>(`/jobs/${jobId}/check-folder`, {
    method: "POST",
  });
}

export function setSkills(
  jobId: number,
  skills: Omit<SkillRequirement, "id">[]
): Promise<SkillRequirement[]> {
  return apiFetch<SkillRequirement[]>(`/jobs/${jobId}/skills`, {
    method: "PUT",
    body: JSON.stringify(skills),
  });
}

export function getSkills(jobId: number): Promise<SkillRequirement[]> {
  return apiFetch<SkillRequirement[]>(`/jobs/${jobId}/skills`);
}

export function getServiceAccountEmail(): Promise<{ email: string }> {
  return apiFetch<{ email: string }>("/jobs/service-account");
}
