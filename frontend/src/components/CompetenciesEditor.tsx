import { useId } from "react";
import { COMMON_COMPETENCIES } from "../services/competencies";

interface Props { values: string[]; onChange: (values: string[]) => void; disabled: boolean }

export default function CompetenciesEditor({ values, onChange, disabled }: Props) {
  const id = useId();
  const isCommon = (value: string) => COMMON_COMPETENCIES.some(item => item.toLowerCase() === value.trim().toLowerCase());
  const custom = values.filter(value => !isCommon(value));
  return <section className="setup-section" aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`}>Additional competencies <span className="setup-help">(optional)</span></h2>
    <p className="setup-help" id={`${id}-help`}>Find resume mentions or supporting activities for the Job Match Summary. These competencies do not affect scores or exclusions. Resume evidence does not verify ability.</p>
    <fieldset className="setup-fields" disabled={disabled} aria-describedby={`${id}-help`}>
      <legend className="competency-legend">Choose competencies relevant to this JD</legend>
      <div className="competency-choices">
        {COMMON_COMPETENCIES.map(name => <label className="mandatory-control" key={name}>
          <input type="checkbox" checked={values.some(value => value.trim().toLowerCase() === name.toLowerCase())}
            onChange={event => onChange(event.target.checked ? [...values, name] : values.filter(value => value.trim().toLowerCase() !== name.toLowerCase()))} />
          {name}
        </label>)}
      </div>
      <label className="setup-field" htmlFor={`${id}-custom`}>Other nontechnical competencies
        <textarea id={`${id}-custom`} rows={3} value={custom.join("\n")}
          onChange={event => onChange([...values.filter(isCommon), ...event.target.value.split("\n")])}
          placeholder="e.g. Teamwork" aria-describedby={`${id}-custom-help`} />
      </label>
      <p className="setup-help" id={`${id}-custom-help`}>One per line, up to 20 competencies total. Custom competencies match their explicit names. Keep DSA in Skills &amp; Requirements so it can be scored.</p>
    </fieldset>
  </section>;
}
