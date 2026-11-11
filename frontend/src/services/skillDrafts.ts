import type { SkillRequirement } from "../types";

export type SkillInput = Omit<SkillRequirement, "id">;
export type SkillDraft = Omit<SkillInput, "aliases"> & { key: string; aliasesText: string };

export function newSkillDraft(skill?: SkillRequirement): SkillDraft {
  return {
    key: crypto.randomUUID(),
    skill: skill?.skill ?? "",
    description: skill?.description ?? "",
    mandatory: skill?.mandatory ?? false,
    importance: skill?.importance ?? 3,
    required_evidence_level: skill?.required_evidence_level ?? 1,
    assessment_method: skill?.assessment_method ?? "resume",
    aliasesText: (skill?.aliases ?? []).join(", "),
  };
}

export function skillInputs(drafts: SkillDraft[]): SkillInput[] {
  return drafts.map((draft, index) => {
    if (!draft.skill.trim()) throw new Error(`Enter a skill for requirement ${index + 1}, or remove it.`);
    const seen = new Set<string>();
    const aliases = draft.aliasesText.split(/[,\n]/).map(value => value.trim()).filter(value => {
      const key = value.toLocaleLowerCase();
      if (!value || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    return {
      skill: draft.skill.trim(), description: draft.description?.trim() || null,
      mandatory: draft.mandatory, importance: draft.importance,
      required_evidence_level: draft.required_evidence_level,
      assessment_method: draft.assessment_method, aliases,
    };
  });
}
