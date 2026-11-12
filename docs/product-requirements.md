# Product requirements

Reconciled on 12 November 2026 against the chat **Assess project idea feasibility**
(the final consolidated workflow and subsequent Drive clarification), plus the
current project's later implementation choices. Older proposals for manual
uploads and server-rendered HTML were superseded.

## Stack retained

React + TypeScript + Vite; Python + FastAPI; SQLAlchemy + asyncpg with Neon
PostgreSQL; Google Identity Services; read-only Google Drive service account;
PyMuPDF; the existing small Sentence Transformer/ONNX direction; deterministic,
versioned Python scoring. Planned hosting remains a Render Static Site and Free
Web Service. This reconciliation introduces no replacement framework, database,
model provider, or paid hosting requirement.

## Recruiter workflow

1. Verified Google sign-up/sign-in; account name/email are automatic. Public sign-up
   is enabled by default following the later request to admit new Google accounts;
   administrator approval remains configurable. Each account owns its jobs and results.
   A subsequent request adds username/password registration and sign-in as an
   alternative, without a Google account or email. Google remains available;
   local accounts use a unique username, Argon2id password hash and the same ownership rules.
2. Create or reopen an owned JD: title, description, Drive folder link, optional company/team.
3. Share the folder with the app service account as Viewer, copy its email and check access.
4. Configure requirements, review the folder and requirements, then initiate assessment.
5. See sequential processing progress and separate passed, excluded and failed outcomes.
6. See a basic ranking of passing candidates, completeness, extracted information and export.

App credentials are configured once. Each recruitment folder must grant read
access; a shared parent can supply inherited permissions. A link alone grants no
permission. Originals are never moved, changed or deleted.

## Requirement controls

| Setting | Agreed behavior |
| --- | --- |
| Skill | Searchable suggestions with manual entry; recruiter confirms the final list |
| Requirement description | Intended application of that skill |
| Mandatory | Visible checkbox; explicit presence gate, separate from numerical ranking |
| Importance | Discrete 1–5 scoring weight, with current value and meaning |
| Required evidence level | Separate discrete 1–5 expected evidence category |
| Assessment method | Resume or Interview, configurable per requirement |
| Approved aliases | Expandable matching settings; only explicitly approved alternatives |

Interview-assessed requirements retain Mandatory, but expose no numerical
scoring controls, infer no evidence level, and contribute no weight to the
resume score. Mandatory interview requirements still require explicit presence.

The evidence ladder is: 1 Mention/basic; 2 Coursework/program; 3 Applied project;
4 Internship; 5 At least six months of relevant skill-linked work experience.
Use the highest clearly supported category, preserving its source passage and
rule. Dates for an unrelated role do not establish duration for every skill.
Weak evidence receives a lower category; ambiguous evidence is undetermined.
These categories describe resume claims, not verified competence.

## Processing and scoring

- Discover accessible, non-trashed PDFs directly inside the selected folder;
  follow pagination, freeze file IDs/versions and requirement configuration.
- Process one resume at a time, initially with one active assessment. Release
  file resources and save progress after each outcome. No groups of five.
- Start with English, selectable-text PDFs under configured size/page/time/file
  limits. OCR, recursive folders, multilingual support and large workloads are deferred.
- Extract text with source pages and blocks. Unreadable/encrypted/unsupported
  documents are processing failures, not missing-skill exclusions.
- Check explicit mandatory names and approved aliases with boundaries and
  negation handling before detailed analysis. Semantic similarity cannot pass this gate.
- Missing any mandatory requirement stops further analysis, scoring and ranking
  for that resume. Retain the missing requirements and operational status.
- For passing resumes, extract skills, projects, education and experience;
  preserve source passages and support corrections/reassessment.
- Retrieve relevant passages per requirement using explicit matches/aliases and
  semantic retrieval. Do not substitute one whole-resume similarity score.
- Intended evidence credit: min(supported level / required level, 1). Skill credit
  combines supported relevance and evidence credit; overall score is the weighted
  mean across resume-assessed requirements, scaled to 100. This is a provisional
  scoring policy requiring labelled evaluation, not a probability of job success.
- Absent optional skills receive zero credit. Undetermined evidence provisionally
  receives zero credit with its weight retained and assessment marked incomplete.
- Preserve ties; rank all passing candidates together. Live ranking is provisional.
  All-interview configurations have no numerical ranking. Names, contact details
  and institution names do not contribute to skill scores.

## Persistence, hosting and delivery boundaries

Neon now supplies the persistent storage left undecided in the earlier briefing.
The implemented durable intake queue extends the earlier interrupted-run design
with checkpoint/restart recovery; it does not establish hosted unattended completion.
Keep the current snapshot and recovery behavior.

The Render backend should wake on use with bounded readiness checks and clear
errors, without scheduled keep-alives. Measure memory and cold-start behavior on
its actual host. Deployment limits remain to be verified.

Google sign-in and live Drive/Neon intake are verified locally. The UI now covers requirement configuration, initiation, saved history, progress,
ranked results, source-linked evidence and CSV export. Basic section extraction,
ONNX passage matching, evidence categories and weighted scoring are implemented.
Manual corrections/reassessment, broader parser coverage, and model/rubric
calibration remain outstanding. The detailed explainable dashboard,
continuous folder monitoring and OCR remain deferred. Do not present intake-only
results as completed candidate analysis or ranking.
