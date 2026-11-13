# Additional competencies and Job Match Summary

Job setup has an optional **Additional competencies** section below Skills &
Requirements. Choose Communication, Leadership and Influence, Problem-Solving
and Critical Thinking, or Learning Agility. Add other nontechnical names one per
line (maximum 20 names, 100 characters each). Save, then initiate a new assessment.
DSA belongs in scored Skills & Requirements, not in this reporting section.

## Product behavior

Additional competencies never change the technical score, its denominator,
mandatory eligibility, completeness flag or rank. Missing evidence brings no
penalty or exclusion. They are frozen with the job inputs for each assessment;
editing a job does not change an older run.

Reporting distinguishes:

- **Supporting activity:** a bounded English-language rule finds a relevant
  activity, such as presenting findings to stakeholders or mentoring a team.
- **Listed:** the resume names the competency (or a configured built-in phrase),
  without a recognized supporting activity.
- **Not evidenced:** no supported mention or recognized activity is found.

The built-in activity rules describe communication, leading/mentoring others,
investigating/resolving problems, and learning/adopting new tools. Custom names
match explicit phrases only. Negated and future-only claims are not treated as
supporting activity. No personality, interview ability, speed of learning or
professional competence is verified. Rules are conservative heuristics, can miss
paraphrases and context, and require human review and labelled validation.

## Results and CSV

Open an assessed resume to see its **Job Match Summary** and unscored competency
findings with page references. The CSV adds a **Job Match Summary** column to the
existing rank, filename, match score and completeness columns. It briefly covers
each technical requirement's evidence alignment/gaps and each selected additional
competency. All text is a deterministic paraphrase/template, not a quotation from
the resume or an assertion that the candidate should be selected.

For example:

> Technical requirements — Python: application; meets requested evidence.
> Additional competencies (unscored) — Communication: Describes presenting or
> explaining work to others; Learning Agility: Not evidenced in the resume.

Only passing, assessed resumes enter ranked results/export, as before. Missing
mandatory technical requirements still exclude before analysis. Interview-coded
requirements in existing jobs retain their prior unscored behavior; they are not
silently moved to this section.

## Storage and compatibility

Run `python -m app.core.migrate` from `backend` before starting this version on an
existing database. Revision `0002_additional_competencies` adds the JSON column
`jobs.additional_competencies` with an empty-list default; it does not overwrite
jobs, accounts, scores, snapshots or source documents. Fresh databases are also
supported. The application reports a required upgrade instead of silently using
an outdated schema.

New snapshots freeze `summary_version=job-match-summary-v1`, separately from
`analysis_version=resume-evidence-v2`. Analysis JSON holds the summary and findings.
Old snapshots default to no reporting version; saved results stay untouched, the
new CSV cell is empty, and the UI explains that a new assessment is needed.

Inference stays local with the existing ONNX model. No external LLM, paid token
API, new model dependency or change to the selected stack was added.

## Verification — 2026-11-13

- All 167 backend unittest tests passed: persistence/ownership/validation,
  frozen reporting inputs, missing/negated/future signals, paraphrase reporting,
  score invariance, legacy compatibility, CSV and migration preservation.
- Five frontend Node tests and the TypeScript/Vite production build passed.
- The migration ran twice on an isolated development clone. Counts and hashes
  of saved snapshots/documents stayed unchanged, and old jobs received empty
  competency lists. It was then applied to development. The temporary branch
  was deleted after explicit user authorization.
- A disposable live job/account exercised HTTP, the persistent worker, shared
  Drive, actual pinned ONNX inference, Neon persistence, result details and CSV.
  All 15 PDFs reached terminal outcomes: 2 assessed, 12 mandatory exclusions,
  1 processing failure. All assessed rows carried the requested reporting data.
  Existing saved results and Drive originals stayed unchanged; disposable
  records were removed.
- A synthetic selectable-text PDF, parsed through PyMuPDF and analysed with the
  actual ONNX model, produced the same technical score/credits/completeness with
  and without competency reporting. The four built-in activity signals and a
  listed custom competency were reported separately from the score.
- Browser checks rendered the actual job/setup and result components using
  synthetic data. Checkbox/custom editing, DSA validation, saving, initiation
  navigation and summary/details display passed. Measured geometry at 390,
  1440 and 1728 px showed no spacing/overflow findings for captured elements.

These checks establish local product operation, not comprehensive language-rule
accuracy or hosted capacity. Render deployment and labelled validation remain
separate work.
