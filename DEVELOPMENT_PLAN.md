# TeamFlow development plan

Source: full-history fork of [Akanichi/kanban-board](https://github.com/Akanichi/kanban-board), `master` at `a41a00515b77e3ef61cfe4a7a0b3889c497e44b0`, verified 2026-10-03. Preserve the original MIT license and Mohamed Akaarir attribution. Audit evidence is in [docs/UPSTREAM_CLAIMS_AUDIT.md](docs/UPSTREAM_CLAIMS_AUDIT.md). This plan predates implementation and makes no release claim.

## Inherited foundation and affected architecture

Retain React/TypeScript/Vite, FastAPI, SQLAlchemy, account registration/login, teams/boards/tasks, priority/due-date fields, task cards, comments, labels, checklist data and attachment metadata. Existing HTTP routes live in `backend/app/routers`; `models.py`/`schemas.py` are the inherited model boundary. Reusable authorization, transaction/order logic, invitation workflow, activity and attachment storage will be separate focused modules. Avoid duplicate backend checks and discard no inherited feature without a documented replacement.

## Exact authorization policy

Use team roles `owner`, `admin`, `member` and board roles `admin`, `member`. Team ownership has a single explicit `owner_id`; the owner cannot be removed or demoted except through atomic transfer to an existing member. Team admins manage normal members and invites; only owners manage admins/delete teams/transfer ownership. Team membership is required for explicit board membership.

| Operation | Owner | Team admin | Normal member | Unrelated authenticated user |
| --- | --- | --- | --- | --- |
| View team / member list | Yes | Yes | Yes | No |
| Rename team | Yes | Yes | No | No |
| Invite/remove ordinary members | Yes | Yes | No | No |
| Change admin roles / transfer / delete team | Yes | No | No | No |
| Create board | Yes | Yes | No | No |
| View team board | Yes | Yes | Yes | No |
| View private board | Yes | Yes | Explicit board member | No |
| View public-read board | Yes | Yes | Yes | Yes |
| Edit tasks/subresources | Yes | Yes | Team board member or explicit private/public-read board member | No |
| Manage columns, WIP, board members / delete board | Yes | Yes | Explicit board admin | No |
| Delete another author's comment / attachment | Yes | Yes | Explicit board admin | No |
| Delete own comment / attachment | Yes | Yes | With current board edit permission | No |

All application APIs require authentication, including public-read views. `public-read` grants view only to authenticated outsiders; it never grants edit. Team members may edit team-visible boards; private/public-read write permission requires explicit board membership unless team owner/admin. Authorization must follow a guessed subresource ID to its real board. Membership removal closes existing WebSocket eligibility on later event checks and removes inaccessible frontend state.

## Confirmed vulnerabilities and regression-first work

Before route fixes, encode unauthorized task/label/comment/checklist/attachment access and public-read mutation as failing tests with Owner A, Admin A, Member A and unrelated User B. Test board creation URL/body mismatch, unrelated assignment, revoked board access and owner invariants. Remove Authorization/token logging and internal exception details. Server policy remains authoritative even when frontend buttons are hidden.

## Schema and migration plan

Replace production `create_all()` startup with Alembic. The inherited revision parents exist, but the no-op root never creates base tables; do not claim that chain works. Build an explicit deterministic base migration and additive TeamFlow migration, portable across SQLite/PostgreSQL. Include preflight recognition/import of the upstream ORM-created schema with data-preserving role/column/position/attachment backfills. Document backup, migration/stamp steps and downgrade limits; never require database deletion.

Add owner/visibility/revision, persisted board columns, nullable WIP limit, task column FK and canonical positions, invitation token hashes/expiry/used/revoked state, append-only activities, private attachment metadata and necessary checks/unique indexes. Canonical active ordering is zero-based and contiguous per board column; archived tasks do not count toward WIP. Foreign keys and deletion/cascade behavior must be verified on both engines.

## Ordering, concurrency and WIP

Expose one task move request with target column/index and required `expected_revision`; reject stale state with HTTP 409 and current revision. All board mutations serialize through a database compare-and-swap update of the board revision before reading/modifying task state. Recheck authorization after acquiring serialization. PostgreSQL row updates and SQLite transactional writer serialization protect the same board across workers; do not rely on process-local locks.

Within the transaction, read sorted source/target cards, remove moved card, insert at a bounded index, enforce target WIP, temporarily park affected positions to avoid immediate unique collisions, then assign contiguous canonical positions. Commit all updates once. Task create/delete/archive/restore participate in the same serialization and WIP/order rules. Columns cannot be deleted while active or archived tasks reference them; users move or delete those tasks explicitly. WIP reduction below current count returns a conflict. No stale request may increment the durable revision or append success activity.

## Activity and real-time design

Record immutable actor/action/entity/details/board/team activity rows in the same transaction as changes; no update/delete API. Publish only after successful commit, with board ID and resulting revision, to authenticated subscribers of that board. Use short-lived single-use WebSocket tickets obtained via authenticated HTTP; avoid JWT query strings. At connection and publication verify current board view policy. Clients ignore old revisions and fetch authoritative state on gaps/reconnect/conflict. Broadcast fails must not undo committed database state. Document single-process in-memory fanout limits unless distributed transport is actually implemented and tested.

## Attachment design

Remove public `/uploads` serving. Store files outside static roots under generated random keys, preserve safe display filename separately, enforce bounded streaming size and a small extension/content allowlist (PDF, text, PNG, JPEG), reject active HTML/SVG/script content and traversal. Metadata exposes an authenticated download API, never storage paths. Upload/download/delete use real board policy; delete requires uploader or board admin. Use forced download and nosniff headers. Stage files, roll back/delete on failed DB write, remove metadata transactionally and clean files safely; retain upstream files through an explicit private migration/backfill path. Test mismatch, over-limit, unauthorized IDs, traversal, cleanup and legacy attachments.

## Authentication and invitations

Choose access-token-only sessions with explicit re-login; remove unsupported refresh claims. Require a configurable strong secret, expiration/type validation and safe logging. Invitations use cryptographically random tokens, store only hashes, bind team/email/role/expiry, validate signed-in account email, reject replay/revocation/expiry, and atomically create membership. Copyable invite links are implemented; email delivery is outside v1 unless verified.

## Frontend reconciliation

Use backend state for columns/tasks/revision/members/permissions and one move request. Preserve filtering, priorities, dates, archive, labels, comments, checklists and upload/download workflow. Clear board/task state when switching team/board/account; eliminate global board-data localStorage. Provide working role/invite/assignment/column/WIP/activity controls with actionable errors. Re-fetch and reconcile on 409 instead of keeping an optimistic stale order. Show connection state and resynchronize after reconnect.

## Baseline and testing strategy

Use a project-local Python virtual environment, locked frontend dependencies, disposable SQLite databases and a disposable PostgreSQL instance. Capture exact versions/commands/exits in `docs/BASELINE.md`; do not use personal databases. Tests are not upstream functionality.

- Backend: authorization matrix and direct-ID cases; owner transfer/member administration; invitation normal/expired/revoked/replay/wrong-email/already-member cases; persisted column CRUD, WIP and archive; same/different-column moves, duplicates/no-op/bounds/cross-board moves, simultaneous requests on independent connections; immutable committed activities; private attachment validation/cleanup/download; two same-board and one different-board WebSocket clients; fresh/upstream-data migrations.
- Frontend: role rendering, invite acceptance, authoritative column rendering, single move request and 409 reconciliation, WIP error, account/board-switch state reset, protected download behavior and WebSocket revision gaps/reconnect. Build and lint are additional gates.
- Integration: actual PostgreSQL migrations/API tests and concurrent ordering/WIP checks; report exact pass/fail status, never infer support from portable-looking SQL.
- CI/manual: GitHub Actions executes relevant checks; multi-user task-create/move/comment acceptance verifies only same-board clients receive committed events. Browser smoke tests exercise actual inherited and added controls.

## Ordered milestones and release gates

1. Preserve/full-history clone, verify HEAD/license; save audit/plan, then run isolated baseline.
2. Add regressions; centralize authorization, ownership and config; replace migration mechanism.
3. Implement roles/invitations and persisted columns/WIP; serialize task mutations with revision CAS.
4. Add transactional activity and secure attachments; implement authenticated board WebSockets after permissions work.
5. Reconcile frontend; run backend/frontend/migration/concurrency/WebSocket tests and actual PostgreSQL checks.
6. Review complete diff and requirements; write accurate architecture/security/setup/API/release docs. Create `FINAL_REPORT.md` only after release completion, recording actual limitations and check outputs.
7. After all gates pass, publish a new public repository under the authenticated account without overwriting an existing repository, retain `upstream`, inspect hosted CI and fix/reverify any failed jobs.

Make logical local commits after validated milestones. Publication requires user-authorized scope already specified by this request, but success cannot be claimed before push and hosted CI evidence. Every release gate must report passed, failed or unverified; unfinished roadmap features must not appear as released capabilities.

## Implementation decision recorded during development

The final v1 WebSocket design authenticates using the access token in the first WebSocket message within five seconds, with an explicit origin allowlist, token expiration and repeated current-board eligibility checks. This replaces the proposed ticket workflow above while keeping credentials out of URLs/logs. Real-time fanout remains in-memory and single-worker; database concurrency protection is independent of that deployment limitation.
