# Username/password accounts

Lucid supports username/password registration and sign-in alongside the existing
Google Identity Services button. A local account requires no Google account or
email address. It uses the same recruiter ownership rules and JWT sessions.

## Use the form

Select **Create account**, enter a username, password and matching confirmation,
then submit. Public registration signs the user in immediately. Later use the
same username/password under **Sign in**. Google remains an independent option;
Google SDK loading/errors do not block the local form.

Usernames contain 3–40 ASCII letters/numbers/dots/underscores/hyphens and start
with a letter or number. The backend trims usernames and stores them lowercase;
they are case-insensitive and unique. Passwords contain 12–128 characters and
cannot consist only of spaces. Spaces and Unicode in a valid password are
preserved exactly; passwords are never trimmed or case-folded. Paste, browser
autocomplete and password managers are supported.

No email is collected, so email verification and self-service forgotten-password
recovery are not implemented. Password change and account linking are also not
implemented. Google and local registrations create separate identities; similar
names never merge accounts or transfer access to existing jobs.

## API and approval

- `POST /auth/register`: JSON `username`, `password`; returns 201 plus session
  and recruiter profile. Duplicate username returns 409. Invalid input returns
  422 without echoing the submitted password.
- `POST /auth/password`: same JSON; returns session/profile. Unknown user and
  wrong password both return 401 with the same message.
- `GET /auth/me`: existing protected profile; `email` may be null and `username`
  is present for local accounts. Google accounts retain their existing IDs/email
  and have a null username. Password hashes are never returned.
- `ALLOW_PUBLIC_SIGNUP=true`: both registration methods are open. Pending accounts
  become approved only after successful credential verification.
- With public signup false, local registration creates a pending account and
  returns 403; a valid password cannot bypass administrator approval. The
  Google email allowlist does not auto-approve a local username.

## Password handling

`argon2-cffi` hashes passwords with Argon2id: 19 MiB, time cost 2, parallelism 1,
random per-password salts. These parameters follow the
[OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
Verification checks whether rehashing is needed. Unknown users still undergo a
dummy hash comparison. Raw passwords are not stored, included in JWTs, returned
in validation errors, written to localStorage or logged by application code.
Database SQL parameter logging remains hidden.

Hashing runs off the async event loop, with at most two concurrent allocations
per process. In-memory, five-minute attempt windows allow 10 registrations per
resolved peer address, 30 logins per peer, and 10 logins per username. A limit
returns 429 with Retry-After. The server does not read a user-supplied forwarding
header to bypass those buckets. Configure trusted proxy handling at deployment.
The limiter holds at most 4096 active buckets, resets on restart and is not
shared across workers/instances. Replace it with a shared limiter before scaling
the current single-process API. HTTPS is required for hosted password submission.

## Existing database upgrade

Run from `backend` before starting the updated backend:

```powershell
..\.venv\Scripts\python.exe -m app.core.migrate
```

The command initializes missing application tables, then runs Alembic revision
`0001_password_accounts`. Existing recruiters gain nullable `username` and
`password_hash` fields and a unique username index. `google_id` and `email`
become nullable to support local identities. Existing Google values/IDs,
ownership and assessment foreign keys are preserved. Version tracking uses
`alembic_version`; repeating an upgrade is safe. There is no automatic downgrade
that drops passwords or local accounts.

The command uses `DATABASE_DIRECT_URL` when supplied. Otherwise it uses the
existing URL, removing a Neon `-pooler` hostname suffix for a direct migration
connection with the same database/role/credentials. Do not replace it with
another project. A fresh database can also be
initialized by this command. Startup detects an old account schema and gives an
upgrade instruction rather than serving a partially upgraded authentication API.

The Google service-account key is still needed to read shared Drive folders.
Using a local Lucid account changes how a recruiter signs in, not how Google
Drive folder sharing works. Share the folder with the displayed service-account
email as Viewer, exactly as before.
