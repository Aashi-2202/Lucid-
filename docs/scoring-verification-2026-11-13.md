# Evidence-fulfilment scoring verification — 2026-11-13

New assessments freeze `resume-evidence-v2`. Each resume-assessed requirement
earns `min(supported evidence level / required evidence level, 1)` credit. The
overall percentage is the importance-weighted mean of those credits. Cosine
similarity retrieves evidence and breaks ties between equally supported
passages; it no longer multiplies requirement credit.

Explicit names or approved aliases must be linked to a concrete application in
the same bounded clause to receive application credit. Generic project claims,
learning statements and unrelated nearby actions do not establish that link.
Semantic-only associations stay undetermined with zero provisional credit.
Missing mandatory presence still excludes before analysis. Optional missing
requirements retain their weights; interview requirements remain unscored.

## Verification performed

- All 154 backend unittest tests passed, including weighted arithmetic, partial
  credit, low-cosine explicit applications, unsupported semantic associations,
  evidence grounding, mandatory exclusion, API/export and legacy compatibility.
- Three frontend Node tests and the TypeScript/Vite production build passed.
- Browser checks used synthetic data rendered by the actual assessment page:
  current requirement-credit details, the saved-policy notice, and completed
  results with undetermined evidence marked provisional/Needs review.
- Measured section/table geometry at 390, 1440 and 1728 px showed no spacing or
  horizontal-overflow findings for the captured elements.
- A disposable account/job exercised the running local HTTP API, persistent
  worker, actual shared Drive PDFs, pinned ONNX model and Neon development DB.
  All 15 files reached terminal outcomes: 2 assessed, 12 mandatory exclusions,
  1 processing failure. Disposable job/results/account were removed afterwards;
  no Drive file or existing user assessment was changed.
- The previously reported 37.5 result was reproduced under its original v1
  snapshot. A fresh v2 run of the same two configured level-3 requirements scored
  100, supported by specific application evidence for both requirements. The
  saved original remained 37.5. This verifies the policy change, not an externally
  validated proficiency judgement or a target percentage chosen in advance.

## Applying the change

Refresh the local application, reopen a saved JD and initiate a **new assessment**.
Existing assessments retain their frozen v1 scoring and display a policy notice.
No database migration or overwrite of old results is required.

The evidence ladder and bounded language rules remain heuristics requiring
labelled validation and human review. A score of 100 means the configured resume
evidence targets were met; it does not verify competence, completed delivery or
job performance. This local verification does not establish Render deployment
or hosted memory/cold-start capacity. Additional competencies and the planned
Job Match Summary CSV column are separate pending work.
