# Upstream claims audit

Audit date: 2026-10-03. Source: [Akanichi/kanban-board](https://github.com/Akanichi/kanban-board), `master`, commit `a41a00515b77e3ef61cfe4a7a0b3889c497e44b0`.

This records the inherited source before TeamFlow implementation. The full Git history was cloned; the audited commit is present and is the current functional `master` HEAD. The other newer remote branches inspected are dependency update branches, not later functional changes on `master`. The canonical MIT license and `Copyright (c) 2024 Mohamed Akaarir` remain unchanged.

`IMPLEMENTED` means concrete source supports the feature, not that it passed the TeamFlow release gates. `PARTIAL` means usable pieces exist with missing policy or workflow. `ABSENT` means the claimed implementation could not be found. `BROKEN` means source demonstrates a contradictory or nonfunctional path. `UNVERIFIED` means runtime evidence is still needed. Baseline command results belong in `docs/BASELINE.md` when completed.

| README claim | Status | Concrete evidence and practical limit |
| --- | --- | --- |
| JWT authentication / password hashing | IMPLEMENTED | `backend/app/routers/auth.py` registers and authenticates users; `auth/utils.py` hashes with Passlib/bcrypt and issues HS256 tokens with expiration; `auth/deps.py` resolves users. The default signing secret is insecure and token/header logging leaks credentials. |
| Token refresh | ABSENT | No refresh endpoint, refresh token persistence, rotation or client refresh flow exists in `backend/app` / `frontend/src`. |
| Session management | PARTIAL | `frontend/src/contexts/AuthContext.tsx` stores access token/user in localStorage and clears them on logout. There is no server session revocation; expired sessions require re-login. |
| WebSocket real-time updates | ABSENT | `main.py` registers only HTTP routers; no WebSocket route or board subscription exists, and frontend service calls use Axios. Dependency names and README architecture examples provide no runtime implementation. |
| Drag and drop | PARTIAL | `frontend/src/App.tsx:handleDragEnd` makes one moved-task request followed by individual sibling position updates. `routers/tasks.py:update_task` shifts integer positions without revision checks or a serialized board mutation. Concurrent moves are not protected. |
| Priority / due dates | IMPLEMENTED | `models.Task`, `schemas.TaskBase/TaskUpdate`, task update routes and task detail controls store priorities and due dates. |
| Task assignment | PARTIAL | `task_members`, `Task.assigned_to`, response schema and avatars exist. Task create/update schemas have no assignment mutation; `TaskDetailsModal.tsx` contains `/* Implement user assignment */`. There is no validated assignment workflow. |
| Teams / board membership | PARTIAL | `models.TeamMember/BoardMember` and `routers/teams.py` implement membership and membership removal. Team creation commits separately from initial membership; board creation trusts body `team_id` independently of URL `team_id`. |
| Role-based access control | PARTIAL | Roles `admin` / `member` gate some membership routes; the last-admin removal guard exists. There is no owner role/transfer invariant and task mutations reuse a read-like access helper. Public boards skip membership checks entirely. |
| Team invitations | ABSENT | `POST /teams/{team_id}/members` immediately inserts an existing user by ID. There is no invitation model, token, expiry, acceptance or revoke workflow. |
| Activity logging | ABSENT | Logging statements exist, but no immutable activity table, transactional events, feed endpoint or frontend activity feed exists. Debug logging is not product activity history. |
| Customizable columns | BROKEN | Columns have no database table. `App.tsx` writes local `kanban_columns` shared by accounts/boards, while rendered `boardColumns` remains three hardcoded statuses. Add-list changes are not an authoritative persisted workflow. |
| Filtering / sorting | PARTIAL | Frontend label filter exists; columns sort cards by `position`. There is no complete server-side multi-field query/search workflow. |
| Board sharing | PARTIAL | Explicit board membership and `is_public` exist. `tasks.py:check_board_access` treats public as unrestricted access for all authenticated users, including mutation, while board endpoints use different checks. No public-read/write separation exists. |
| Archive functionality | PARTIAL | `Task.is_archived`, update schema and task-card archive behavior exist. `read_tasks` includes archived records and the main board does not consistently separate archive history. |
| Labels | PARTIAL | Task labels and mutation routes exist; all three label routes lack authentication/board authorization. Globally reused label rows and removal without task membership validation need correction. |
| Comments | PARTIAL | Comment create/list/delete and UI exist; list lacks authentication and create lacks board access. Delete verifies author but not current board membership. |
| Checklists | PARTIAL | Checklist JSON and add/toggle routes exist; both mutation routes lack authentication/authorization. No shared revision guard protects concurrent checklist edits. |
| Attachments | PARTIAL | Upload/list and frontend links exist. Upload lacks board authorization, original filename contributes to storage path, there is no size/type validation, and `main.py` publicly mounts `/uploads`. Lists are unauthenticated and internal exceptions are returned. |
| SQLite | IMPLEMENTED | `database.py` constructs a SQLite engine with `check_same_thread=False`. Runtime baseline is recorded separately. |
| PostgreSQL | UNVERIFIED | README mentions PostgreSQL, but runtime `database.py` hardcodes SQLite instead of using configured `DATABASE_URL`. No PostgreSQL service, integration test or CI evidence exists upstream. |
| Alembic migrations | BROKEN | Five revision files exist with their referenced parents present. Root revision `e9f4cf25a184` and final `0f9401067cde` are no-ops; intermediate revisions modify a `tasks` table never created by the chain. Some operations are not SQLite portable. Startup `Base.metadata.create_all()` is the effective schema path. A fresh migration chain cannot create the model schema. |
| React Query / Socket.io networking | ABSENT | Actual application state uses React hooks/Context and Axios; there is no query-provider/subscription workflow backing those claims. |
| Documented API / architecture / UUID schema | BROKEN | README diagrams show files/hooks not present. Models use integer IDs and status strings, while README examples show UUIDs and a column foreign key. Register/login paths, request bodies and response statuses also differ. |
| Automated coverage / robust concurrency | ABSENT | No upstream test suite or CI release gates were found. No board revision, WIP model or concurrency invariant is represented in models/routes. |

## Confirmed source defects to preserve as regression cases

- An unauthenticated client can invoke label/checklist mutations and read labels, comments and attachment metadata by task ID.
- An authenticated unrelated user can comment/upload to a guessed task ID. Any authenticated unrelated user passes public board task mutations.
- Public static uploads bypass authorization entirely, including private-board files.
- Authorization headers are logged in `main.py:log_requests`; token prefixes/payloads are logged in `auth/utils.py:verify_token`.
- Engine configuration ignores `settings.DATABASE_URL`; startup schema creation conceals the broken migration chain.
- Drag requests consist of independently committed sibling updates; there is no CAS revision, WIP enforcement or DB uniqueness invariant.

## Disposable runtime reproduction

`work/baseline_probe.py` was run against a throwaway upstream database with pinned backend dependencies (bcrypt 4.0.1, pytest 8.4.2, HTTPX 0.27.2 and Alembic 1.17.2 in the isolated virtual environment). OpenAPI returned 200. Anonymous reads of a private task's labels, comments and attachments returned 200. Anonymous checklist creation returned 500 during response serialization, but inspection confirmed the unauthorized checklist persisted. An unrelated authenticated user creating a task on a public board likewise received 500 while the unauthorized write persisted. These are successful unauthorized commits even though upstream response serialization subsequently fails.

`work/baseline_migrations.py` tested a fresh database with the correct Alembic script location and failed at revision `a5c315ff7db7` with SQLite `no such table: tasks`. The parent chain exists; its root is a no-op and never creates the table. No WebSocket endpoint was present. Exact baseline logs/commands are retained by the root agent and will be recorded in `docs/BASELINE.md`.

Missing invitations, WebSockets, column persistence, activity history and validated assignment are TeamFlow additions; they are not described as improvements to functioning upstream implementations.
