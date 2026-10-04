# TeamFlow

Collaborative Kanban with enforceable roles, atomic task ordering, WIP limits, private attachments, activity history and authenticated board WebSockets.

## Overview

TeamFlow extends [Akanichi/kanban-board](https://github.com/Akanichi/kanban-board) at upstream commit `a41a00515b77e3ef61cfe4a7a0b3889c497e44b0`. It retains the upstream Git history, React/FastAPI foundation and original MIT license. The implementation audit in [docs/UPSTREAM_CLAIMS_AUDIT.md](docs/UPSTREAM_CLAIMS_AUDIT.md) distinguishes working source from unsupported upstream README claims.

A board mutation is a database transaction: authorize the actor, serialize against the board revision, enforce ordering and WIP, persist the change and activity, then notify subscribers. Clients reconcile with the committed server snapshot.

## Features

### Upstream foundation

Inherited account registration/login, team/board/task models and CRUD, task cards and drag/drop concepts, priorities, due dates, filters, archive concepts, labels, comments, checklist data and attachment metadata. These were already substantial parts of the original project; TeamFlow does not claim to have invented them. Baseline failures and authorization gaps are recorded in [docs/BASELINE.md](docs/BASELINE.md).

### TeamFlow additions

- Central backend team and board policy with owner/admin/member roles, ownership transfer, explicit board membership and read-only sharing.
- Hashed, expiring, single-use invitations tied to the accepting account's email; copyable links and revocation.
- Persisted, configurable columns with server-enforced WIP limits.
- Transactional, contiguous task ordering with board revision compare-and-swap, stale request conflicts, and concurrent final-slot protection.
- Validated assignments and protected comment, label, checklist and file operations.
- Committed actor/action/entity activity records and board-scoped WebSocket notifications.
- Private generated file storage, authenticated downloads, validation, rollback cleanup and explicit legacy import.
- Alembic fresh/legacy migrations, SQLite and actual PostgreSQL verification, regression suites and CI configuration.
- Permission-aware React workflows, optimistic move rollback, account-scoped cache cleanup, reconnect handling and keyboard move controls.

## Screenshots

Real browser captures using fake `example.test` accounts and a disposable workspace. See [browser acceptance](docs/MANUAL_ACCEPTANCE.md) for reproduction and limits.

| Board | Task details |
| --- | --- |
| ![TeamFlow board](docs/screenshots/board.png) | ![Task details](docs/screenshots/task-details.png) |

| Team members and invitations | Activity history |
| --- | --- |
| ![Team members](docs/screenshots/team-members-invitations.png) | ![Committed activity](docs/screenshots/activity.png) |

| WIP conflict and rollback | Mobile board |
| --- | --- |
| ![WIP conflict](docs/screenshots/wip-conflict.png) | ![Mobile board](docs/screenshots/mobile.png) |

Additional captures: [tablet](docs/screenshots/tablet.png), [mobile task details](docs/screenshots/mobile-task-details.png).

## Technology Stack

| Layer | Implementation |
| --- | --- |
| Frontend | React 18, TypeScript 5.6, Vite 6, Axios, TanStack Query 5 |
| Interaction | `@hello-pangea/dnd`, Headless UI dialogs, CSS and Tailwind 4 with its official PostCSS plugin |
| Backend | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Uvicorn |
| Identity | PyJWT HS256, Argon2 via pwdlib; legacy bcrypt login upgrade |
| Storage | SQLite for local use; PostgreSQL 17 integration verification; Alembic |
| Real-time | Native browser WebSocket and FastAPI WebSocket endpoint |
| Tests | pytest, FastAPI TestClient, Vitest, React Testing Library; local Playwright browser acceptance |

Python 3.12 is locally verified; Python 3.13 is configured in CI. Node 24 is the frontend baseline. Exact backend versions are in `requirements-dev.lock`, and frontend versions are in `frontend/package-lock.json`. See [verification evidence](docs/VERIFICATION.md) and the [dependency audit record](docs/DEPENDENCIES.md).

## Architecture

```mermaid
flowchart LR
    UI[React workspace] -->|Bearer REST| API[FastAPI routers]
    UI <-->|Authenticated board WebSocket| WS[Board channel manager]
    API --> Policy[Central authorization policy]
    API --> TX[Board revision / domain transaction]
    TX --> DB[(SQLAlchemy / SQLite or PostgreSQL)]
    TX --> Activity[Activity in same transaction]
    Activity --> DB
    TX -->|After commit| WS
    API --> Files[Private attachment storage]
    Migrations[Alembic migrations] --> DB
```

The inherited `models.py`, schema boundary, routers and React components remain recognizable. Reusable modules hold authorization, ordering, activity, invitations, private files and real-time delivery. There is no production `create_all()` startup path. Frontend server state belongs to TanStack Query; access tokens remain in memory.

## Authorization Model

All collaboration REST and WebSocket access requires an authenticated account. The server resolves each guessed task/subresource ID to its actual board before granting access.

| Operation | Team owner | Team admin | Team member | Unrelated account |
| --- | --- | --- | --- | --- |
| Read team roster | Yes | Yes | Yes | No |
| Rename team | Yes | Yes | No | No |
| Create board | Yes | Yes | No | No |
| Invite/remove ordinary member | Yes | Yes | No | No |
| Invite/promote/demote/remove admin | Yes | No | No | No |
| Transfer ownership / delete team | Yes | No | No | No |
| Read/edit tasks and subresources | Yes | Yes | Board policy | Public-read view only |
| Manage board, columns, WIP, board membership or delete board | Yes | Yes | Explicit board admin | No |
| Delete another actor's comment/file | Yes | Yes | Explicit board admin | No |

Comment authors and file uploaders may delete their own item while they retain board edit permission. A board admin remains a team member and cannot manage team roles through board privileges. The owner cannot be removed or demoted; ownership transfer makes an existing member owner and the previous owner admin. Removing team/board access also clears assignments that are no longer permitted.

## Board Visibility

| Visibility | View | Edit |
| --- | --- | --- |
| `private` | Team owner/admin or explicit board member | Same permitted actors |
| `team` | Every team member | Every team member |
| `public-read` | Every authenticated account | Team owner/admin or explicit board member |

`public-read` does not grant anonymous access or outsider writes. Board membership requires existing team membership. Public projections omit private email addresses and storage paths. Sharing a board ID lets a signed-in account open an authorized shared board.

## Task Ordering

Active tasks have zero-based, contiguous positions within a persisted column. A move calls `POST /api/tasks/{id}/move` with `target_column_id`, `target_index`, `expected_revision` and optional `expected_version`.

An atomic `UPDATE boards ... WHERE revision = expected_revision` obtains database serialization and increments the pending revision. After obtaining it, the server reloads current policy and tasks. It removes the moved card, checks the destination, inserts it at the requested index, temporarily parks affected positions above existing values, then writes canonical positions. A partial unique index protects active `(board_id, column_id, position)` values. All updates and activity commit once.

PostgreSQL serializes through its row update; SQLite serializes transactional writers. No process-local lock is used to protect SQL. Task creation, deletion, archive and restore also normalize ordering. Stale revisions return `409` with current revision; invalid indexes/foreign columns return validation errors. Rejected and no-op moves leave no durable revision or success activity. The frontend rolls back optimistic changes and reloads authoritative state on conflict.

## WIP Limits

A nullable positive column limit counts active tasks only. Creation, incoming movement and restore check capacity inside the serialized transaction. Same-column reorder and moving out remain possible at capacity. Reducing a limit below the current count fails. Two concurrent contenders for the final slot cannot both commit; the losing client receives a conflict and reconciles.

## Real-time Synchronization

`/api/boards/{board_id}/ws` accepts an access token in its **first JSON frame within five seconds**, rather than in a URL. Browser origins are allowlisted. The server checks token expiry and current board view permission at connection, before delivery and during the connection loop.

Only committed board notifications enter that board's channel. Events contain type, board ID, revision and entity/activity identifiers; REST supplies authorized snapshots. The client refetches on events and reconnection, displays connection state, and guards optimistic move reconciliation against older state. Logout closes sockets and clears queries. Publication failure cannot roll back an already committed mutation.

**Deployment constraint:** in-memory fanout requires one Uvicorn worker/one application instance. SQL ordering remains protected across database connections, but multiple application processes need a shared event broker before they can promise cross-process real-time delivery.

## Invitations

Owners/admins create invitations for ordinary members; only owners invite admins. The server generates a random token and stores its SHA-256 hash, team, email, role and expiry. Plaintext is returned once at creation. Invitation lists never return it.

A matching signed-in account can accept an active invitation once. Wrong-account, expired, revoked, replayed, duplicate-pending and already-member cases are rejected. The UI strips the invitation query parameter before login and keeps the pending token in memory. Copy/share the link privately. Email delivery is not implemented.

## Activity History

Actor name, action, entity, timestamp and relevant details are inserted in the same transaction as each change. Board history is authorized and paginated by `before_id` at the API. Team invitation/acceptance records are team-scoped and do not leak into public board history. There is no activity edit/delete API; ORM updates/deletes are rejected. Explicit board/team deletion removes related data through cascades, so this is project history rather than an external compliance archive.

## Attachments Security

Files use random generated storage keys outside static roots. Original names are display metadata. The allowlist is PDF, UTF-8 text, PNG and JPEG, with extension/content checks and a default 10 MiB limit. Path-like/reserved names, mismatches, active HTML/SVG/script types and oversized files are rejected.

Upload requires board edit permission; download requires board view permission; deletion requires current edit permission plus uploader or board admin. Downloads use authenticated HTTP, forced attachment disposition and `nosniff`. Responses expose no filesystem path or storage key. The old public `/uploads` mount is removed.

Failed metadata transactions remove staged files. Deletion commits metadata before file cleanup. `python scripts/cleanup_attachment_orphans.py` retries orphan cleanup with a minimum one-hour staging grace. Header/signature checks do not provide antivirus scanning or full document sanitization.

## Database Migrations

Run migration commands from `backend/`, with the correct `DATABASE_URL` and a stopped application during an upgrade.

For a **fresh** database:

```powershell
python -m alembic upgrade head
python -m alembic check
```

The active chain is `0001_upstream` (the real inherited schema snapshot) followed by `0002_teamflow` (additive schema and data backfills). The five historical upstream revision files remain under `backend/alembic/legacy_versions/` for attribution and audit; their original no-op root did not initialize a fresh database.

For a **populated upstream** database, first retain the original and use the preflight wrapper:

```powershell
# Example URL must identify the actual upstream SQLite file.
python scripts/upgrade_legacy.py --database-url sqlite:///./kanban.db
python scripts/upgrade_legacy.py --database-url sqlite:///./kanban.db --apply
```

SQLite application creates a timestamped backup through SQLite's backup API before stamping the recognized baseline and migrating. PostgreSQL requires a verified `pg_dump` backup and the additional `--backup-confirmed` flag. The preflight rejects unknown tables/columns/FKs, malformed ownership, case-ambiguous accounts and unsupported revision markers before schema changes. Do not stamp an arbitrary schema manually.

Users, teams, memberships, tasks, comments, checklist JSON and attachment records survive recognized upgrades. Columns are derived from inherited statuses, active positions normalize, owner roles are backfilled and shared labels become board-scoped. Original assignment links remain available while v1 derives one canonical assignee. Legacy public boards become `team` boards, and private boards retain explicit membership access.

Legacy attachment metadata survives; usable bytes require an explicit approved source directory after migration:

```powershell
python scripts/import_legacy_attachments.py --source-dir ./uploads
```

The importer validates and copies files to private random storage without removing originals. Missing/unsafe/unsupported records are reported and their protected downloads return `404`; they are not presented as successfully imported. `0002_teamflow` has no destructive automatic downgrade: restore the pre-upgrade database and original file backup with the previous application version.

## SQLite / PostgreSQL

SQLite enables foreign keys, a busy timeout and transactional writer serialization. It suits a local single-instance workspace. PostgreSQL uses the same SQLAlchemy policy/domain code with `psycopg` and is the production database target, verified locally against a real PostgreSQL 17.11 server. Supply a database/user provisioned for the application and run Alembic before starting Uvicorn.

The integration suite uses separate temporary SQLite files or generated PostgreSQL schemas in a **disposable** database. See [docs/VERIFICATION.md](docs/VERIFICATION.md) for exact commands, results, versions and known warnings.

## Installation

Start in this repository checkout. Use Python 3.12 and Node 24. The following PowerShell commands provide a reproducible development installation:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
Copy-Item .env.example backend/.env
# Print a new secret, then place it in backend/.env as JWT_SECRET.
python -c "import secrets; print(secrets.token_urlsafe(48))"
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Registering creates a personal team, a private board and initial columns transactionally. API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Login uses an OAuth2 form (`username` or email plus `password`), not the old README's JSON login example.

On macOS/Linux activate with `source .venv/bin/activate` and copy the configuration with `cp .env.example backend/.env`; the Python/npm commands remain the same. Production runtime constraints are in `requirements.txt`; the development lock is the exact tested environment.

For PostgreSQL, replace `DATABASE_URL` in the backend environment with `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`, using your provisioned database credentials. A reverse proxy must forward WebSocket upgrades. Use HTTPS/WSS, a private upload volume, a strong secret and explicit frontend origins; run **one worker** until a shared event broker exists.

## Environment Variables

Copy [.env.example](.env.example) to `backend/.env`. Relative database/storage paths resolve from the backend working directory. Environment variables override values loaded from the file.

| Variable | Default / requirement |
| --- | --- |
| `DATABASE_URL` | `sqlite:///./kanban.db`; PostgreSQL SQLAlchemy URL also supported |
| `JWT_SECRET` | Required random signing secret, at least 32 bytes; no production default |
| `ACCESS_TOKEN_MINUTES` | `30`, accepted range 1–1440 |
| `FRONTEND_ORIGINS` | Comma-separated explicit origins or JSON array; no wildcard |
| `UPLOAD_DIR` | `private_uploads`, outside static serving |
| `MAX_UPLOAD_BYTES` | `10485760` (10 MiB), positive |
| `INVITE_HOURS` | `48`, positive |
| Frontend `VITE_API_URL` | `http://localhost:8000/api`; includes `/api` |

Access-token-only sessions require re-login after expiry or a full page reload. There is no refresh-token endpoint, server-side logout revocation or durable browser session. Logout discards local credentials; an already-issued token remains valid until expiry. Tokens and board data are not stored in localStorage/sessionStorage.

## Backend Testing

From the repository root in the activated development environment:

```powershell
python -m ruff check backend
python -m pytest -q --disable-warnings --tb=short
# Set only for a disposable PostgreSQL test database with schema creation permission.
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/teamflow_test'
python -m pytest -q --disable-warnings --tb=short
Remove-Item Env:TEST_DATABASE_URL
```

Coverage includes direct foreign-ID denial, roles/ownership, invitation security, ordering and threaded database concurrency, final-slot WIP contention, private files/import/cleanup, rollback activity, channel isolation, expiry/revocation and fresh/populated legacy migrations. Exact current totals are recorded in [verification evidence](docs/VERIFICATION.md).

## Frontend Testing

```powershell
cd frontend
npm ci
npm test
npm run lint
npm run build
```

Vitest/RTL cover permissions, WIP/stale move rollback, logout cache cleanup, invitation forms/acceptance, activity and WebSocket refetch/reconnect. [docs/MANUAL_ACCEPTANCE.md](docs/MANUAL_ACCEPTANCE.md) records the local Playwright acceptance harness and fake multi-user scenario. Browser acceptance is local-only; it is not claimed as a hosted CI job.

## GitHub Actions

[.github/workflows/ci.yml](.github/workflows/ci.yml) configures Python 3.12/3.13 SQLite checks, a real PostgreSQL 17 service running the backend suite, and Node 24 frontend tests/lint/build. Backend CI installs `requirements-dev.lock`; frontend CI uses `npm ci`. The workflow runs on pushes to `master`/`main` and pull requests with read-only repository permissions.

Local passes do not establish a hosted Actions pass. Publication and hosted workflow results are recorded separately after execution.

## Accessibility

Headless UI dialogs provide focus management and Escape dismissal; form inputs have labels, buttons have accessible names, and status/error messages are announced. Task controls offer move-to-column and up/down buttons in addition to drag/drop. Permission-aware views display read-only status. Small screens intentionally scroll the board horizontally while dialogs and navigation fit the viewport. This has browser and component verification, but no formal accessibility certification.

## Project Structure

```text
backend/
  app/
    models.py, schemas.py           inherited ORM/schema boundary
    routers/                        authentication, teams, boards, tasks
    authorization/policy.py         reusable team/board policy
    domain.py                       database revision serialization
    tasks/                          input schemas, ordering, domain helpers
    invitations/                    token lifecycle and acceptance
    activity/                       transactional activity/commit helpers
    attachments/                    private files and protected endpoints
    realtime/                       authenticated board subscriptions
  alembic/                          fresh and additive migrations
  scripts/                          legacy upgrade/import, orphan cleanup
  tests/                            isolated API/domain/migration regressions
frontend/
  src/components/                   adapted board/task/auth and settings UI
  src/contexts/                     in-memory session lifecycle
  src/hooks/                        move reconciliation and WebSocket lifecycle
  src/services/                     typed authenticated HTTP operations
  src/test/                         Vitest and React Testing Library coverage
  e2e/                              local Playwright browser acceptance
docs/                               audit, baseline, verification, screenshots
.github/workflows/                  SQLite/PostgreSQL/frontend CI
```

## Known Limitations

- WebSocket fanout is in-memory and requires one application process; distributed delivery and durable event replay are not implemented.
- Access-token-only sessions require re-login; no refresh, logout token revocation, OAuth login or password reset.
- Invitations are shared through links; SMTP delivery is not implemented.
- One canonical task assignee; legacy many-to-many assignment links are preserved during migration.
- WIP and revision conflicts are rejected rather than automatically merging edits. Metadata editing uses authorized serialization; expected revisions are mandatory for task movement and optional for column reordering (the UI supplies them).
- Activity pagination is available in the API; the current panel displays the recent page. Deleting a project removes its history.
- Files receive bounded type checks, not malware scanning. File cleanup after a process crash may require the orphan maintenance command.
- No Docker/deployment bundle or production hosting is claimed. Local browser acceptance and configured CI are distinguished from hosted execution.
- Tailwind 4 targets modern browsers; only installed Chrome was exercised in the browser acceptance run. See [browser requirements](docs/DEPENDENCIES.md).
- Known SQLite expression-index reflection and Starlette TestClient deprecation warnings are documented with independently tested behavior.

## Roadmap

Shared event broker, durable event catch-up, optional notification/mention delivery, board templates and audit export are possible future work. They are not released features.

## Acknowledgements

[Mohamed Akaarir's Akanichi/kanban-board](https://github.com/Akanichi/kanban-board) provides the original application and history. The original README acknowledged Cursor AI Composer and Anthropic Claude assistance. TeamFlow's added work is documented in the audit, plan, tests and subsequent Git commits; it does not claim exclusive authorship of the inherited project.

## License

[MIT](LICENSE). The canonical upstream license remains unchanged, including **Copyright (c) 2024 Mohamed Akaarir**.
