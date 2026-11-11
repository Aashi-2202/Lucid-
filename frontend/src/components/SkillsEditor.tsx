import { useId } from "react";
import { newSkillDraft } from "../services/skillDrafts";
import type { SkillDraft } from "../services/skillDrafts";

const COMMON_SKILLS = [
  "Python", "SQL", "Java", "JavaScript", "TypeScript", "React", "Node.js",
  "FastAPI", "Django", "C", "C++", "C#", ".NET", "PostgreSQL", "MongoDB",
  "Git", "Docker", "Kubernetes", "AWS", "Azure", "Google Cloud", "Excel",
  "Power BI", "Tableau", "Data analysis", "Machine learning", "Statistics",
  "Communication", "Leadership", "Project management",
].sort((a, b) => a.localeCompare(b));

const IMPORTANCE = ["", "Nice to have", "Low", "Moderate", "High", "Critical"];
const EVIDENCE = ["", "Mention / basic", "Coursework / program", "Applied project", "Internship", "At least 6 months of relevant work experience"];

interface Props {
  skills: SkillDraft[];
  onChange: (skills: SkillDraft[]) => void;
  disabled: boolean;
}

export default function SkillsEditor({ skills, onChange, disabled }: Props) {
  const listId = useId();
  function update<K extends keyof SkillDraft>(key: string, field: K, value: SkillDraft[K]) {
    onChange(skills.map(skill => skill.key === key ? { ...skill, [field]: value } : skill));
  }
  return (
    <section className="setup-section" aria-labelledby="requirements-title">
      <h2 id="requirements-title">Skills &amp; Requirements</h2>
      <p className="setup-help">Search suggestions or enter a custom skill.</p>
      <datalist id={listId}>{COMMON_SKILLS.map(skill => <option key={skill} value={skill} />)}</datalist>
      {skills.length === 0 && <p className="setup-help">No requirements added. Add a skill to configure screening.</p>}
      {skills.map((skill, index) => {
        const id = `skill-${skill.key}`;
        const interview = skill.assessment_method === "interview";
        return (
          <fieldset className="skill-card" key={skill.key} disabled={disabled}>
            <legend>Requirement {index + 1}</legend>
            <div className="skill-heading">
              <label className="setup-field" htmlFor={`${id}-name`}>
                Skill *
                <input id={`${id}-name`} list={listId} value={skill.skill} required maxLength={255}
                  onChange={event => update(skill.key, "skill", event.target.value)}
                  placeholder="Search skills or enter a custom skill" autoComplete="off" />
              </label>
              {!disabled && <button type="button" className="setup-link remove-skill"
                aria-label={`Remove requirement ${index + 1}`}
                onClick={() => onChange(skills.filter(item => item.key !== skill.key))}>Remove</button>}
            </div>
            <label className="setup-field" htmlFor={`${id}-description`}>
              Requirement description
              <textarea id={`${id}-description`} rows={2} value={skill.description ?? ""}
                onChange={event => update(skill.key, "description", event.target.value)}
                placeholder="e.g. Use Python to build data processing pipelines" />
            </label>
            <div className="skill-options">
              <div>
                <label className="mandatory-control">
                  <input type="checkbox" checked={skill.mandatory}
                    onChange={event => update(skill.key, "mandatory", event.target.checked)} aria-describedby={`${id}-gate`} />
                  Mandatory
                </label>
                <p className="setup-help" id={`${id}-gate`}>Missing skill or approved alias → excluded.</p>
              </div>
              <label className="setup-field" htmlFor={`${id}-method`}>
                Assessment method
                <select id={`${id}-method`} value={skill.assessment_method}
                  onChange={event => update(skill.key, "assessment_method", event.target.value as "resume" | "interview")}>
                  <option value="resume">Resume</option>
                  <option value="interview">Interview</option>
                </select>
              </label>
            </div>
            {interview && <p className="setup-help" id={`${id}-interview`}>Interview: no resume score. Mandatory presence still applies.</p>}
            {!interview && <div className="skill-sliders">
              <label className="setup-field" htmlFor={`${id}-importance`}>
                <span>Importance: <strong>{skill.importance}</strong> / 5</span>
                <input id={`${id}-importance`} type="range" min={1} max={5} step={1} value={skill.importance}
                  aria-valuetext={`${skill.importance} of 5: ${IMPORTANCE[skill.importance]}`}
                  aria-describedby={interview ? `${id}-interview` : `${id}-importance-help`}
                  disabled={interview} onChange={event => update(skill.key, "importance", Number(event.target.value))} />
                <span className="setup-help" id={`${id}-importance-help`}>{IMPORTANCE[skill.importance]} · Scoring weight</span>
              </label>
              <label className="setup-field" htmlFor={`${id}-evidence`}>
                <span>Required evidence level: <strong>{skill.required_evidence_level}</strong> / 5</span>
                <input id={`${id}-evidence`} type="range" min={1} max={5} step={1} value={skill.required_evidence_level}
                  aria-valuetext={`${skill.required_evidence_level} of 5: ${EVIDENCE[skill.required_evidence_level]}`}
                  aria-describedby={interview ? `${id}-interview` : `${id}-evidence-help`}
                  disabled={interview} onChange={event => update(skill.key, "required_evidence_level", Number(event.target.value))} />
                <span className="setup-help" id={`${id}-evidence-help`}>{EVIDENCE[skill.required_evidence_level]}</span>
              </label>
            </div>}
            <details className="matching-settings">
              <summary>Matching settings · Approved aliases{skill.aliasesText.trim() ? " (configured)" : ""}</summary>
              <label className="setup-field" htmlFor={`${id}-aliases`}>
                Approved aliases
                <textarea id={`${id}-aliases`} rows={2} value={skill.aliasesText}
                  onChange={event => update(skill.key, "aliasesText", event.target.value)}
                  placeholder="e.g. Python3, Python 3" aria-describedby={`${id}-aliases-help`} />
              </label>
              <p className="setup-help" id={`${id}-aliases-help`}>Separate with commas or new lines. Only these approved alternatives match.</p>
            </details>
          </fieldset>
        );
      })}
      {!disabled && <button type="button" className="setup-secondary" onClick={() => onChange([...skills, newSkillDraft()])}>+ Add Skill</button>}
    </section>
  );
}
