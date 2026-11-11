/**
 * Shared TypeScript types for the Lucid frontend.
 * Mirrors backend Pydantic schemas.
 */

export interface Recruiter {
  id: string;
  email: string;
  name: string;
}

export interface JobDraft {
  id: string;
  title: string;
  description: string;
  folder_link: string;
  company?: string;
  recruiter_email: string;
}

export interface SkillRequirement {
  skill: string;
  description: string;
  mandatory: boolean;
  importance: number; // 1-5
  required_evidence_level: number; // 1-5
  assessment_method: "resume" | "interview";
  aliases: string[];
}

export interface AssessmentProgress {
  assessment_id: string;
  total: number;
  processed: number;
  passed: number;
  excluded: number;
  failed: number;
  status: "queued" | "processing" | "completed" | "interrupted";
}

export interface CandidateResult {
  rank: number;
  file_name: string;
  score: number;
  complete: boolean;
}
