# Username/password accounts with Gmail verification

New username accounts require a Gmail address and an emailed verification code.
Existing username accounts without an email retain their login and owned jobs.
Google Identity Services remains available independently.

## Signup

Choose Create account, enter username, Gmail, password and confirmation, then
select Send verification code. Enter the six-digit emailed code and choose
Verify and create account. No account/session exists before verification.
Public signup signs in after verification; approval-only mode creates a pending
verified account and returns 403.

Usernames remain unique and case insensitive: 3–40 ASCII letters/numbers/dots/
underscores/hyphens, starting with a letter or number. New passwords require
**8–128 characters and at least one ASCII special character**, such as !, @, #
or _. Spaces do not count as special characters. Valid passwords preserve
whitespace and Unicode exactly. Existing passwords retain their login behavior.

Codes expire in 10 minutes, are single use, and permit five incorrect attempts.
Resends require 60 seconds, replace the previous code, extend expiry, preserve
attempt counts and allow at most three resends. Change signup details restarts
the flow. Password/code state is cleared when its step completes. Only completed
sessions/profiles are stored in browser localStorage, never signup passwords/codes.

Gmail/Googlemail addresses are trimmed and lowercased; googlemail.com becomes
gmail.com. Dot/plus aliases are not canonicalized to one physical inbox. Existing
usernames and stored emails cannot be claimed or automatically merged. If Google
login finds an email linked to a username account, use that username/password.
Password reset/change, adding mail to an existing account, and explicitly linking
Google login to a username identity remain separate work.

## Sender setup

Set these only in ignored backend/.env or host secrets:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=sender@gmail.com
SMTP_FROM_EMAIL=sender@gmail.com
SMTP_PASSWORD="your-app-password"
```

Gmail requires 2-Step Verification and an eligible account for App Passwords:
[Google guidance](https://support.google.com/accounts/answer/185833).
Keep the sender credential out of chat, Git and frontend variables. Other
SMTP providers use the same settings; implicit TLS supports SMTP_SECURITY=ssl,
normally on port 465. TLS certificates/hostnames are verified, there is a
15-second socket timeout, and plaintext fallback is never used.

Without credentials, signup returns an explicit 503 without creating an account
or fake verification success. Existing sign-ins remain available. SMTP acceptance
is not proof of inbox delivery; check actual delivery/spam with a configured
sender and recipient. Sender failures are redacted and cannot activate a code.

## API

- POST /auth/register: username, email, password; returns 202 with challenge_id,
  expires_in and resend_after. No token or code is returned.
- POST /auth/register/verify: challenge_id, code; returns 201 with session/profile
  on success. Expired/replaced/reused codes fail; duplicate username/email is 409.
- POST /auth/register/resend: challenge_id; sends a replacement subject to limits.
- POST /auth/password: username, password; unknown/wrong credentials return the
  same 401. It does not apply the new registration password policy.
- GET /auth/me: existing protected profile. Legacy email can be null. Hashes,
  digests and pending signup data are never returned.

## Storage, throttles and migration

Passwords use salted Argon2id: 19 MiB, time cost 2, parallelism 1, outside the
async event loop with two concurrent allocations maximum. Unknown users undergo
a dummy comparison. Pending signup stores the password hash and an HMAC-SHA256
code digest bound to challenge/email using the server JWT secret. No plaintext
code/password is persisted or logged by application code.

Five-minute in-memory windows allow ten signup starts per peer, thirty logins
per peer, ten logins per username, ten resends per peer and thirty code checks
per peer. Email requests are limited to five per address per hour per process.
Per-challenge attempt/resend counters persist in the database; conditional
mutations enforce one-time consumption atomically with account creation.
Temporary challenges expired for more than a day are removed on later signups.

In-memory throttles are bounded to 4096 buckets, reset on restart and are not
shared across workers. Add a shared limiter before scaling beyond one API
process. Configure trusted proxy handling and HTTPS on a host. User-supplied
forwarding headers do not reset the limiter.

Run from backend before starting this version on an existing database:

```powershell
..\.venv\Scripts\python.exe -m app.core.migrate
```

Revision 0003_email_verification adds nullable recruiters.email_verified_at and
email_verifications. It preserves existing hashes, Google IDs, approvals, jobs
and assessments. A fresh verified Google login records its verification time;
migration does not falsely mark old emails verified. The upgrade is repeatable
and uses the existing direct URL (or removes the supplied pooled URL's pooler
suffix). No new project or auth stack is introduced. Automatic destructive
downgrades are refused.

Drive sharing is unchanged: share the resume folder with the service-account
email as Viewer.

## Verification — 2026-11-13

- 179 backend tests passed, including the existing screening product and new
  expiry, replacement-code, single-use/concurrency, attempt limits, secret
  redaction, SMTP TLS and legacy-account cases.
- Seven frontend tests and the TypeScript/Vite production build passed.
- Browser checks exercised the actual signup components with a synthetic
  transport: Gmail entry, special-character errors, code-step focus, wrong-code
  feedback, resend notice and completed signup. Measured geometry at 390, 1440
  and 1728 px had no spacing findings. Touch emulation and throttled mobile
  network behavior were not tested.
- The Neon development migration ran twice in a transaction and was rolled
  back after checking account/result preservation, then applied normally.
- A disposable signup exercised the ASGI API and actual Neon persistence with
  captured mail transport. It could not log in before verification, verified
  once, persisted its linked email/timestamp, then logged in. Disposable records
  were removed and no external email was sent by that check.

Real Gmail authentication and inbox delivery remain unverified until an eligible
sender credential is configured. SMTP mock/capture tests are not a claim of live
email delivery.
