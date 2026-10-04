# TeamFlow final report

Release date: 2026-10-04, Asia/Shanghai. Verified implementation source: `09b99551ea2545298a2ce5d279b7bd7c401a6d99`. Local verification, independent review, public repository creation, preserved-history push and the corrected implementation's actual hosted workflow are complete. All four hosted jobs passed after a WebSocket finalization defect was reproduced and fixed. This report identifies that immutable source run; its release-documentation commit is checked separately after publication.

## 1. Upstream repository

[Akanichi/kanban-board](https://github.com/Akanichi/kanban-board), retained as the `upstream` remote. TeamFlow extends the existing React/FastAPI project.

## 2. Upstream commit used

`a41a00515b77e3ef61cfe4a7a0b3889c497e44b0`. The audited commit was the functional upstream master HEAD. Newer inspected remote branches contained dependency update proposals rather than later functional master changes.

## 3. License status

MIT remains unchanged, including `Copyright (c) 2024 Mohamed Akaarir`. Both the original and current `LICENSE` have Git blob `57eef89ba33a2491a74512e789a076acd8ad57bf`. Upstream attribution remains in the README and audit.

## 4. Git history preservation

The repository is not shallow. The upstream commit is an ancestor of the release source. At implementation source `09b9955`, master contains 22 reachable commits: 12 inherited commits and ten TeamFlow milestones. No history replacement or force push was used. The original remote remains `upstream`; the new public repository is `origin`.

## 5. Upstream README claims audit

[UPSTREAM_CLAIMS_AUDIT.md](docs/UPSTREAM_CLAIMS_AUDIT.md) classifies claims as implemented, partial, absent, broken or unverified, with source evidence and disposable runtime reproductions. [BASELINE.md](docs/BASELINE.md) records baseline startup, lint/build and migration results. Upstream had authentication and substantive Kanban models/UI, but lacked claimed refresh tokens, WebSockets, invitations and transactional activity. Columns were not persisted, PostgreSQL configuration was ignored, and fresh Alembic initialization failed because the root never created the tasks table.

## 6. Inherited functionality

Account registration/login, React/FastAPI structure, team/board/task CRUD foundations, task cards and drag-and-drop concepts, priorities, due dates, filters, archive fields, labels, comments, checklist JSON and attachment metadata. These inherited features are acknowledged separately from the TeamFlow additions.

## 7. TeamFlow functionality added

Central authorization and owner/admin/member roles; ownership transfer; private/team/public-read board visibility; hashed invitations; persisted configurable columns and WIP limits; atomic ordering with board revisions; validated assignments; transactional activity; private file storage/downloads; authenticated board WebSockets; real fresh/legacy migrations; SQLite/PostgreSQL regression suites; account-scoped frontend state, rollback/reconnect workflows and responsive accessible controls.

## 8. Confirmed vulnerabilities fixed

Direct guessed-ID and unauthenticated label/comment/checklist/attachment access now resolves and authorizes the actual board. Unrelated users cannot mutate public-read tasks. Public static file serving and original-filename storage paths were replaced with authorized private storage and validated generated keys. Authorization-header/token debug logging and the insecure default signing secret were removed. Token claims and algorithms are checked, new password hashes use Argon2, and successful legacy bcrypt logins upgrade hashes. [RELEASE_REVIEW.md](docs/RELEASE_REVIEW.md) additionally records corrected assignment permission drift, legacy private assignment/label collisions and an old-session HTTP 401 race. The review is not external security certification.

## 9. Final architecture

React 18/TypeScript/Vite uses Axios and TanStack Query for bearer-authenticated REST state and a native WebSocket for committed board notifications. FastAPI routers call shared authorization and domain transaction modules. SQLAlchemy persists users, teams, board members, columns, tasks, invitations and activity in SQLite or PostgreSQL; Alembic initializes/upgrades the schema. Private file bytes live outside static roots. Database changes and activity commit before board notifications are published.

## 10. Authorization policy

All collaboration HTTP and WebSocket access requires authentication. Every task/subresource request derives its actual board before granting access. Team roles come from current database membership rather than a role claim in the token. Board administration does not grant team administration. Permission changes serialize with board mutations and clear assignments that lose edit eligibility.

## 11. Team role matrix

| Operation | Owner | Admin | Member |
| --- | --- | --- | --- |
| Read team roster | Yes | Yes | Yes |
| Rename team/create board | Yes | Yes | No |
| Invite/remove ordinary members | Yes | Yes | No |
| Invite/promote/demote/remove admins | Yes | No | No |
| Transfer ownership/delete team | Yes | No | No |
| Read/edit tasks and resources | Yes | Yes | Board policy |
| Manage board/columns/WIP | Yes | Yes | Explicit board admin |

The owner cannot be removed or demoted. Transfer selects an existing member and makes the former owner an admin. Unrelated accounts have no team privileges; public-read board viewing is the explicitly permitted exception.

## 12. Board visibility model

`private`: team owner/admin and explicit board members can view/edit. `team`: every team member can view/edit. `public-read`: every authenticated account can view, while edits remain limited to team owner/admin and explicit board members. No anonymous collaboration or outsider writes are granted. Public projections omit email addresses and file storage paths.

## 13. Invitation design

Cryptographically random tokens are stored only as SHA-256 hashes with team, normalized email, intended role, expiry and state. Plaintext is returned once at creation, never in invitation lists. Acceptance binds to the signed-in matching email, rejects expired/revoked/replayed/already-member cases, and consumes the token in the membership transaction. Owner/admin can invite members; only the owner can invite admins. The UI removes the invitation query parameter before login and holds it in memory. Links are copied/shared; SMTP delivery is not implemented.

## 14. Column model

Persisted board columns have stable IDs, names, zero-based positions and optional positive WIP limits. Tasks reference their board's column. Board-admin operations create, rename, reorder and delete empty columns; limits cannot be reduced below the active task count. Foreign-board column IDs are rejected.

## 15. Task ordering algorithm

For a move, remove the task from its source list, validate the destination/index and WIP, then insert at the target index. Temporarily park affected positions above existing values before assigning contiguous zero-based canonical positions. A partial unique index protects active `(board_id, column_id, position)` values. Source/destination positions, the moved task's version, board revision and activity persist in one transaction. Create/delete/archive/restore normalize affected active ordering. No-op and rejected moves leave no durable revision or success activity.

## 16. Board revision/concurrency model

Moves require `expected_revision` and accept optional task `expected_version`. An atomic board-row update with the expected revision serializes mutations using PostgreSQL row locking or SQLite transactional writer serialization. Policy and task state are reloaded after serialization. Stale clients receive HTTP 409 and the current revision. Ordering does not depend on a process-local lock. The frontend rolls back rejected optimism and reloads authoritative state; newer WebSocket snapshots win over late responses.

## 17. WIP enforcement

Capacity counts active tasks only. Task creation, incoming movement and archive restore check WIP inside the serialized transaction. Reordering within a full column and moving out remain permitted. Invalid limits and reductions below current count fail without partial changes.

## 18. Concurrent WIP behavior

Threaded database tests on both engines race two contenders for one remaining slot: only one commits and the other conflicts. Activity/revision/order reflect only the successful transaction. Browser acceptance also observes actual HTTP 409, rollback notice and exactly two cards in a column limited to two.

## 19. Assignment validation

One canonical assignee must currently be allowed to edit the board. Read-only unrelated accounts cannot be assigned. Team/board removal, visibility restrictions and role demotion reconcile active and archived assignments inside existing board locks, increment task versions and record assignment activity. Legacy migration deterministically derives an eligible canonical assignee while retaining original many-to-many assignment links.

## 20. Activity event design

Actor/name, action, entity, timestamp and relevant details are inserted with the domain mutation in the same SQL transaction. Rejected operations and failed commits create no success activity. API pagination uses `before_id`; the UI shows recent history. Invitation activity remains team-scoped. There is no activity edit/delete API and ORM modification is rejected; explicit project deletion cascades history, so it is not an external compliance archive.

## 21. Comment/checklist/label authorization

Each resource resolves the task's current board and applies view/edit policy. Labels are board-scoped and normalized; checklist entries have stable IDs. Comment authors may delete their own comments while retaining edit permission; board admins can moderate. Foreign resource IDs, unauthenticated access and outsider mutations are denied.

## 22. Attachment security design

Allowlisted PDF, UTF-8 text, PNG and JPEG files receive extension/content validation and a default 10 MiB size limit. Path-like/reserved names and active HTML/SVG/script types are rejected. Exclusive random storage keys place bytes in a private directory; responses expose no key/path. Downloads require view permission and force attachment disposition with `nosniff`; deleting requires current edit permission plus uploader or board-admin status. Failed metadata commits remove staged bytes; committed deletions precede cleanup, with a grace-aware orphan cleanup CLI. Legacy imports require an explicit approved source directory and preserve original bytes. Validation is not antivirus scanning or full document sanitization.

## 23. WebSocket authentication

The first JSON frame must supply an access token within five seconds. Tokens are not placed in query URLs. Origin allowlisting, token expiry and current board-view policy apply at connection, before delivery and during the connection loop. Access revocation disconnects protected channels; heartbeat frames do not trigger frontend data polling.

Finalization cancels and drains receiver/delivery tasks inside a narrow AnyIO shield so session cancellation cannot interrupt cleanup. A deterministic regression failed before the fix and passed afterward; cancellation is not broadly caught or suppressed. This follows [AnyIO's finalization guidance](https://anyio.readthedocs.io/en/stable/cancellation.html#finalization). AnyIO is now an explicit runtime dependency; version 4.15.1 was already in the tested 45-package lock.

## 24. Board-channel isolation

Subscriptions and bounded fanout queues are keyed by board ID. Notifications contain board/revision/entity/activity identifiers, with authorized REST snapshots supplying content. Database tests verify a client connected to another board receives none of the source board's events; guessed board access and revoked membership are rejected.

## 25. Commit-before-broadcast behavior

SQL mutation, ordering, revision and activity commit first. Notification publication happens afterward. Failed database commits produce no success events. A failed broadcast cannot undo an already committed mutation; reconnection/refetch recovers authoritative state. In-memory fanout requires one application worker/instance until a shared broker is implemented.

## 26. Database migrations

The active chain is `0001_upstream` followed by `0002_teamflow`. Historical upstream migrations remain in `backend/alembic/legacy_versions/` for attribution. There is no production `create_all()` startup. Fresh migrations create the real schema; populated upgrades use a strict preflight and backup wrapper before stamping recognized upstream state. Users, teams, memberships, task/resource records and attachment metadata survive; columns/owners/order/board labels and canonical assignees are backfilled. Unknown schemas, malformed references and case-ambiguous accounts are refused. SQLite backups use its backup API; PostgreSQL requires a verified `pg_dump` backup. Downgrade requires backup restoration rather than a destructive automatic path.

## 27. SQLite verification

Complete current suite: **100 passed**, exit 0, 76.32 seconds (81.359 seconds process wall time), including the new shutdown regression. Earlier fresh Alembic upgrade/check and copied real upstream CLI upgrade passed; the corrected hosted SQLite jobs also pass fresh upgrade/check. The original upstream database stayed unchanged and an automatic backup was created. Tests use isolated files, production migration chain and production session options. SQLite enables foreign keys and a busy timeout. Its 21 known warnings concern TestClient deprecation and expression-index reflection; uniqueness is independently tested through database rejection.

## 28. PostgreSQL verification

The same complete current suite passed **100 tests**, exit 0, 118.35 seconds (125.33 seconds process wall time) on actual PostgreSQL 17.11 at a loopback-only disposable cluster. Earlier fresh Alembic upgrade/check passed. Tests use generated schemas, remove only those schemas afterward and share production session options. One known TestClient deprecation warning remains. The corrected actual hosted PostgreSQL 17.11 service job also passed 100 tests in the run linked in section 41.

## 29. Backend tests

Ruff and `pip check` pass. Backend coverage includes roles/foreign IDs, owner invariants, token validation, invitations, ordering/WIP races, assignment lifecycle, private files/import/cleanup, rollback activity/events, channel isolation/expiry/revocation, cancellation-safe WebSocket finalization and fresh/populated migrations. All 45 installed dependencies matched the exact development lock; declaring AnyIO directly added no installed package. Both final 100-test engine runs used the same source/test tree. See [VERIFICATION.md](docs/VERIFICATION.md) for commands, timings and warnings.

## 30. Frontend tests

Clean `npm ci`, lint and TypeScript/Vite production build pass. Vitest 4.1.11 runs **26 passing tests across four files**, covering permissions, optimistic ordering/WIP/stale conflicts, newer snapshots, logout/late responses, WebSocket reconnect, invitations, activity and private download. The released lockfile's observed npm audit has zero reported vulnerabilities. Audit results are time-specific rather than a future guarantee.

## 31. E2E status

Local Playwright 1.63.0 with installed Chrome 154.0.8037.93 reran against the corrected backend and a disposable SQLite workspace: **12 checks passed**, zero page errors, exit 0. It completed at `2026-10-04T06:38:58.595Z` (14:38:58 Asia/Shanghai); the sanitized current report is [browser-shutdown-acceptance.json](docs/browser-shutdown-acceptance.json). The eight published screenshots remain from the earlier visually inspected `2026-10-04T03:46:39.825Z` (11:46:39) run, recorded in [browser-acceptance.json](docs/browser-acceptance.json). The rerun's eight new captures stayed in the isolated workspace and are not published or claimed as visually inspected. Browser E2E is not a hosted Actions job.

## 32. Manual multi-user acceptance test

Independent owner/member/outsider/fresh-invitee browser contexts verified pointer and keyboard dragging, member synchronization through real `task.moved` frames, WIP 409 rollback, exact private download bytes, comments/checklist/labels, committed activity, outsider board/file denial, matching-account invitation acceptance, desktop/tablet/mobile layouts and cleared logout state/storage. [MANUAL_ACCEPTANCE.md](docs/MANUAL_ACCEPTANCE.md) contains the reproducible fake-data walkthrough and harness commands.

## 33. Known limitations

One worker/instance for real-time fanout; access tokens only with re-login on reload/expiry and no server-side logout revocation; no refresh/OAuth/password reset; copied invitations without SMTP; one canonical assignee; recent-page activity UI despite API pagination; no antivirus/full content sanitization; explicit legacy attachment import for available supported bytes. Local browser acceptance is not hosted E2E or production deployment verification. SQLite expression-index reflection and TestClient deprecation warnings remain documented. Public GitHub publication does not host the application.

## 34. Supported Python version

Python **3.12.15** was locally tested with the exact development lock. Hosted CPython **3.12.14 and 3.13.15** both passed their SQLite lint/tests/fresh-migration jobs. PostgreSQL CI uses Python 3.12.14 and also passed. Python 3.13 is hosted-verified rather than locally executed.

## 35. Supported Node version

Node **24** is the supported frontend baseline; local checks used Node 24.18.0 and npm 11.16.0. Actual hosted checks used Node 24.21.0 with `npm ci` and the committed lockfile.

## 36. Exact backend setup commands

From repository root, in PowerShell with Python 3.12 available:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
Copy-Item .env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Place the generated value in `backend/.env` as `JWT_SECRET`; set the intended database URL, private upload directory and explicit origins. Then:

```powershell
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On macOS/Linux use `source .venv/bin/activate` and `cp .env.example backend/.env`. Use one worker until a shared event broker exists. PostgreSQL deployments provide an application database/user and `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`; those are operator-supplied values.

## 37. Exact frontend setup commands

In another terminal, from repository root:

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`; the default API URL includes `/api`. `frontend/.env.example` supports overriding `VITE_API_URL`.

## 38. Exact migration commands

With the application stopped and intended database configured, from `backend/`:

```powershell
python -m alembic upgrade head
python -m alembic check
```

For a recognized populated upstream SQLite database, first retain its original file and use preflight/application:

```powershell
python scripts/upgrade_legacy.py --database-url sqlite:///./kanban.db
python scripts/upgrade_legacy.py --database-url sqlite:///./kanban.db --apply
```

For recognized populated upstream PostgreSQL, substitute the actual connection values and create/verify the backup before application. `pg_dump` uses PostgreSQL connection options; the migration script uses the SQLAlchemy psycopg URL:

```powershell
pg_dump --host HOST --port 5432 --username USER --dbname DATABASE --format=custom --file ./before-teamflow.dump
pg_restore --list ./before-teamflow.dump
$legacyDatabaseUrl = 'postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE'
python scripts/upgrade_legacy.py --database-url $legacyDatabaseUrl
# Pass this flag only after verifying the backup, including a disposable restore.
python scripts/upgrade_legacy.py --database-url $legacyDatabaseUrl --apply --backup-confirmed
```

Optional explicitly approved attachment import:

```powershell
python scripts/import_legacy_attachments.py --source-dir ./uploads
python scripts/cleanup_attachment_orphans.py
```

## 39. Exact test commands

From repository root in the activated development environment:

```powershell
python -m pip check
python -m ruff check backend
python -m pytest -q --disable-warnings --tb=short
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/teamflow_test'
python -m pytest -q --disable-warnings --tb=short
Remove-Item Env:TEST_DATABASE_URL
cd frontend
npm ci
npm test
npm run lint
npm run build
npm audit --json
```

The PostgreSQL URL must identify a disposable database with schema-creation permission. To reproduce local browser acceptance, start the API/frontend with the disposable settings from [MANUAL_ACCEPTANCE.md](docs/MANUAL_ACCEPTANCE.md), then from `frontend/`:

```powershell
$env:TEAMFLOW_ALLOW_DISPOSABLE_SEED = 'yes'
$env:TEAMFLOW_SEED_PATH = Join-Path (Get-Location) 'test-results/seed.json'
$env:TEAMFLOW_EVIDENCE_PATH = Join-Path (Get-Location) 'test-results/browser-acceptance.json'
npm run seed:e2e
npm run test:e2e
```

## 40. Commit summary

| Commit | Actual milestone |
| --- | --- |
| `3282f10` | Upstream audit and invariant development plan |
| `a69b72d` | Authorization and atomic movement regressions |
| `db6fd9b` | Ordering/WIP/private-file/frontend reconciliation gates |
| `14279d2` | Transactional backend and real database migrations |
| `de6cd2e` | Assignment lifecycle, legacy backfills and backend regression expansion |
| `01247f3` | Locked SQLite/PostgreSQL/frontend CI |
| `115c73c` | Responsive frontend workflows, session reconciliation, dependency remediation and browser harness |
| `3a14fa8` | Architecture, release verification docs and real screenshots |
| `b6e5b8e` | Initial public publication report and first successful hosted verification record |
| `09b9955` | Cancellation-safe WebSocket finalization, deterministic regression and explicit existing AnyIO runtime dependency |

The first hosted implementation run passed. The subsequent documentation run exposed intermittent Python 3.13 WebSocket teardown cancellation, which was reproduced deterministically and corrected in `09b9955`. Current local and hosted suites pass 100 tests. The final release-documentation commit refreshes this report and publication evidence; its own workflow is inspected separately after pushing.

## 41. GitHub Actions result

**SUCCESS**, confirmed from actual hosted [run 37183466351](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37183466351) for implementation source `09b99551ea2545298a2ce5d279b7bd7c401a6d99`, completed at `2026-10-04T06:42:52Z`. Each corrected-source job completed successfully:

| Hosted job | Actual conclusion | Job ID |
| --- | --- | --- |
| Frontend, Node 24: clean install, lint, unit tests, production build | Success | `111380509497` |
| Backend PostgreSQL 17 / Python 3.12 integration and migrations | Success | `111380509331` |
| Backend SQLite / Python 3.13: lint, tests, fresh CLI migrations | Success | `111380509461` |
| Backend SQLite / Python 3.12: lint, tests, fresh CLI migrations | Success | `111380509395` |

These are hosted results rather than an inference from local checks. The workflow uses read-only repository permissions, exact backend dependency locks and `npm ci`. Browser acceptance remains local; no hosted browser E2E result is claimed. The final report's documentation commit is verified separately after push, while this report retains the explicitly identified validated implementation source/run.

Inspected corrected-run logs report **100 passed / 21 warnings / 71.54 seconds** on CPython 3.12.14 SQLite, **100 passed / 21 warnings / 68.38 seconds** on CPython 3.13.15 SQLite, and **100 passed / one warning / 115.99 seconds** on CPython 3.12.14 with actual PostgreSQL 17.11. Both SQLite jobs pass Ruff and fresh Alembic upgrade/check. Frontend Node 24.21.0 reports **26 passed across four files**, lint and build success. Hosted action-runtime/image transition notices are maintenance warnings, not job failures.

For chronology, [initial run 37181772257](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37181772257) passed the then-current 99-test implementation at `3a14fa8`. [Documentation run 37182207962](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37182207962) failed on Python 3.13 with 98 passed/one failed: the WebSocket test's body assertions completed, but context teardown raised `CancelledError`. The deterministic regression and narrow finalization shield fixed that lifecycle defect; the corrected run above passed all four jobs. [publication.json](docs/publication.json) preserves the current record and earlier runs.

## 42. Public repository URL

[guxinyihan/teamflow-kanban](https://github.com/guxinyihan/teamflow-kanban). Creation as a new public repository and the initial preserved-history push are confirmed. The original remote is retained separately as `upstream`.
