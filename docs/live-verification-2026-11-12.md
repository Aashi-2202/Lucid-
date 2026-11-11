# Live intake verification — 12 November 2026

Verified the current backend against a real Google Drive folder and the Neon
development database. Drive calls used the configured service account with the
read-only scope. Original Drive files were not modified.

## Observed results

| Check | Result |
| --- | --- |
| Service-account authentication and shared-folder access | Passed |
| Direct PDF discovery and version metadata | 5 PDFs; versions available for all |
| Downloads and isolated intake processing | All 5 reached a terminal intake outcome |
| Selectable-text extraction | 4 ready for analysis: three 1-page PDFs and one 2-page PDF |
| Unsupported input | 1 processing failure with `ocr_required` |
| Neon persistence | Configuration, file list, per-file outcomes and extracted blocks saved |
| Repeated assessment-start request | Same idempotency key returned the same assessment |
| Worker restart | A fresh Python process recovered the first saved file checkpoint and processed the remaining 4 |
| Final progress | `screened`; processed 5; ready 4; failed 1; excluded 0 |

The OCR flag is a parser heuristic, not a manually verified diagnosis of the
entire PDF. OCR remains outside the current intake implementation. A selectable-
text export is needed for that file to enter analysis.

## Method and boundaries

Requests went through the real FastAPI application using an in-process ASGI
transport, normal session-token validation, and the actual Neon database. The
isolated worker made live Drive requests; application services were not mocked.
This did not exercise a running web server or the browser frontend.

A clearly marked technical verification job used one optional, interview-assessed
placeholder requirement. There were no mandatory hiring criteria, inferred
evidence levels, scores, rankings, or candidate-selection decisions. The run does
not establish mandatory-gate accuracy on these resumes. Its synthetic verification
identity was disabled after each phase; its session tokens no longer authorize API
access. The development database retains the verification job and outcomes.

The checkpoint/restart check completed one file, exited the worker process, then
resumed in a new process. Abrupt interruption during a file, expired-lease fencing,
and competing PostgreSQL workers were not exercised in this live run; those
behaviors currently have local integration-test coverage.

At the end of this initial intake check, frontend assessment controls, evidence
classification, semantic relevance, weighted scoring and ranking were pending.
Their subsequent implementation and verification are recorded below. Hosted
memory use and Render cold-start behavior remain unverified.

## Local Google sign-in verification

After the intake run, the backend and frontend were started on local ports 8000
and 5173. Health checks returned HTTP 200 both directly and through Vite's
`/api` proxy; unauthenticated profile requests returned HTTP 401. The Google
sign-in button rendered in the browser.

The user completed Google sign-in in Chrome and confirmed that the Jobs page
opened. A subsequent read of the Neon development database confirmed that the
configured recruiter account exists, is approved, has a Google identity, and
has a recorded login timestamp. The account's email and Google identifier are
omitted here. This verifies local sign-in; it does not verify a hosted origin
or the remaining assessment UI and analysis stages.

Validation for the sign-in changes: 92 backend tests passed with warnings
treated as errors, and the frontend TypeScript/production build passed.

Credentials, folder URLs, source filenames, candidate details, and extracted
resume text are deliberately omitted from this public repository report.

## Full assessment verification

A subsequent local run exercised the running HTTP API, real Drive downloads,
Neon development storage, and the pinned Sentence Transformer ONNX model. A
technical verification job had two optional resume-assessed requirements and an
optional interview-assessed requirement; it did not make hiring decisions.

All 5 PDFs reached terminal outcomes in approximately 52 seconds: 4 were analysed
and scored, and 1 was flagged `ocr_required`. The checks confirmed identical IDs
on repeated start requests, saved analysis with the pinned model revision,
interview requirements omitted from numerical scoring, and downloadable final
CSV rows. Its technical verification identity was disabled afterward. Original
Drive files were unchanged.

The user then initiated their own configured job through Chrome and confirmed
that the assessment page opened. A separate read of Neon confirmed 5 processed:
1 analysed, 3 mandatory-skill exclusions, and 1 processing failure. These are
observed operational outcomes, not manually validated screening decisions.

Validation for the complete assessment changes: 121 backend tests passed with
warnings treated as errors; frontend tests and the production build passed.
Source/evidence categories and relevance thresholds remain initial heuristics.
Manual parser correction/reassessment and hosted deployment verification remain
outstanding.

Browser checks used synthetic UI fixtures for running/completed/all-excluded
states, source details, paused retries, and mobile/desktop layout. The browser
download permission gate did not grant access, so the final browser download
was not completed or retried. CSV generation was verified through the live API.
