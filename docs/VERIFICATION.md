# Verification evidence

Verified on **2026-10-04, Asia/Shanghai**, using isolated workspace runtimes and disposable databases. The local results below are followed by separately inspected hosted GitHub Actions results.

## Backend release checks

| Check | Actual result |
| --- | --- |
| Complete SQLite backend suite | **99 passed**, exit 0, 96.52 seconds |
| Same complete suite on PostgreSQL 17.11 | **99 passed**, exit 0, 134.87 seconds |
| `python -m ruff check backend` | Passed, exit 0 |
| Fresh SQLite `alembic upgrade head` and `alembic check` | Passed; no new upgrade operations detected |
| Fresh PostgreSQL `alembic upgrade head` and `alembic check` | Passed; no new upgrade operations detected |
| Legacy CLI preflight and upgrade of a copy of the actual upstream baseline database | Passed; automatic SQLite backup created; original baseline database unchanged |
| CI workflow YAML parsing and locked-install configuration | Passed |
| Installed dependency compatibility and exact lock comparison | Passed; all 45 installed packages match `requirements-dev.lock` |

The suite timings above are reported by pytest. Measured process wall times were 103.06 seconds for SQLite and 141.64 seconds for PostgreSQL. Both final complete runs used the same source and test tree.

The final fixture uses `autoflush=False` and `expire_on_commit=False`, matching the production session configuration. The full SQLite/PostgreSQL runs above happened after that parity change. Tests use the production Alembic chain rather than ORM `create_all()`. SQLite tests receive separate temporary files; PostgreSQL tests receive separate generated schemas inside a disposable test database and remove only those schemas afterward.

The suite includes role and guessed-ID authorization, owner transfer and removal invariants, public-read write denial, invitation expiry/revocation/replay/wrong-account checks, column/WIP rules, concurrent moves and final-slot WIP contention, stale revisions, archive/assignment/subresource behavior, private attachment validation and cleanup, legacy attachment import, board/team deletion cascades, committed activity and WebSocket events, channel isolation, expired identities, revoked membership, injected commit failure rollback, case-insensitive account uniqueness, and fresh/populated legacy migrations.

Focused authentication checks exercise the HTTP boundary with expired and future-issued identities, missing required claims, wrong issuer/audience/type, unknown accounts, invalid signatures, unsigned tokens and disallowed algorithms. Legacy bcrypt login retains the upstream 72-byte compatibility for the successful login, then upgrades to Argon2 bound to the full password. New passwords distinguish suffixes beyond 72 bytes; malformed stored hashes return 401 without changing the account.

Ordering assertions compare exact task IDs after moves up, down and between populated columns, including source/destination order and absence of loss or duplication. A full WIP column permits reordering and moving work out; an incoming task is admitted only after a slot is freed. The role matrix exercises owner/admin/member/outsider against team settings, board settings, column create/update/delete and WIP, task create/update/delete and activity reads under team/private/public-read visibility.

Assignment lifecycle checks cover active and archived work when visibility changes, role demotion across multiple boards, and preservation of assignments that retain team or explicit board edit access. Legacy migrations choose only eligible private-board assignees while retaining original multi-assignee links, and preserve duplicate labels even when a generated disambiguation name already exists.

Release checks found and corrected timezone-aware invite expiry conversion, duplicate association deletes from loaded child collections, assignment cleanup after visibility/role changes, private-board legacy assignee selection, and repeated legacy label-name collisions. Injecting a real session commit failure verifies that no task, activity row, revision increment or successful WebSocket event survives the failed transaction.

The new label-collision regression initially failed on PostgreSQL because its fixture manually assigned an ID without advancing the serial sequence. The fixture now inserts through the upstream auto-generated ID mechanism and retains every collision/link assertion. The complete 99-test suite was rerun successfully on both engines after that fixture correction.

## Reproduction commands

Run from the repository root after installing the tested development lock in an isolated virtual environment:

```powershell
python -m pip install -r requirements-dev.lock
python -m ruff check backend
python -m pytest -q --disable-warnings --tb=short

# Use a disposable PostgreSQL database with schema creation permission.
$env:TEST_DATABASE_URL = 'postgresql+psycopg://teamflow@127.0.0.1:15432/teamflow_test'
python -m pytest -q --disable-warnings --tb=short
Remove-Item Env:TEST_DATABASE_URL
```

The local verification cluster listened only on `127.0.0.1:15432`. It was an isolated PostgreSQL 17.11 runtime with data outside the released source tree; no operating-system service or personal database was used. The URL above records that disposable local test setup, not a production deployment configuration.

Fresh migration checks used `DATABASE_URL` pointing to a separate disposable database, then ran from `backend/`:

```powershell
python -m alembic upgrade head
python -m alembic check
```

Legacy verification used `python scripts/upgrade_legacy.py --database-url <copied-upstream-database-url>` for preflight, followed by the same command with `--apply`. SQLite application created a timestamped backup before stamping the recognized upstream schema and applying TeamFlow's additive migration. Unknown schemas, missing ownership references and case-ambiguous accounts are rejected before application schema mutation.

## Versions, warnings and CI limits

**Python 3.12.15 was locally verified.** Python 3.13 passed the hosted SQLite job recorded below; it was not locally executed. The frontend CI job uses Node 24; the local machine provides Node 24.18.0 and npm 11.16.0. Backend CI installs all 45 exact dependencies from `requirements-dev.lock`; the PostgreSQL job uses the PostgreSQL 17 service image.

The SQLite run reported **21 known warnings**: Starlette deprecates the HTTPX-based TestClient adapter, and SQLAlchemy/Alembic cannot reflect SQLite expression indexes. The PostgreSQL run reported **one Starlette TestClient deprecation warning**. `--disable-warnings` hides warning details from the terminal but does not remove their count or turn them into verified absence. Case-insensitive index behavior is independently tested through actual database rejection of conflicting inserts on both engines; SQLite's ordinary Alembic metadata comparison does not cover those expression indexes.

## Frontend and browser release checks

The final frontend snapshot was clean-installed and verified on **2026-10-04, Asia/Shanghai**, after the dependency remediation and Tailwind 4 migration.

| Check | Actual result |
| --- | --- |
| `npm ci` from committed lockfile | Passed, exit 0; 419 packages installed |
| `npm audit --json` | Passed, exit 0; zero reported vulnerabilities at every severity |
| `npm test` | **26 passed** across four files, exit 0; Vitest 4.1.11 |
| `npm run lint` | Passed, exit 0 |
| `npm run build` | Passed, exit 0; TypeScript and Vite 6.4.3, 652 modules |
| Real Chrome/Playwright multi-user acceptance | **12 checks passed**, zero uncaught page errors, exit 0 |
| Real application screenshots | Eight refreshed after the CSS pipeline update and visually inspected |

The build produced an initial JavaScript chunk of 332.91 kB (105.30 kB gzip), a lazy board chunk of 212.05 kB (65.28 kB gzip), and 22.24 kB CSS (6.01 kB gzip). These are build artifact sizes, not measured user-performance scores. The final browser run used Chrome 154.0.8037.93 with Playwright 1.63.0 and completed at `2026-10-04T03:46:39.825Z` (11:46:39 Asia/Shanghai).

Frontend regressions exercise role-aware controls, stale/WIP move rollback, exact optimistic ordering, newer snapshots winning over late responses, mutation completion after logout, the delayed old-session HTTP 401 race, WebSocket reconnect/refetch, invitations, private download and human-readable activity details. The browser run observes real `task.moved` frames and HTTP 409 responses, actual pointer/keyboard dragging, correct download bytes, outsider denial, matching-account invitation acceptance and empty browser storage after logout.

The dependency audit is an observed registry result for the released lockfile, not a guarantee against future advisories. See [DEPENDENCIES.md](DEPENDENCIES.md), [MANUAL_ACCEPTANCE.md](MANUAL_ACCEPTANCE.md) and the sanitized [browser report](browser-acceptance.json). Raw local command outputs remain in the isolated workspace's `work/` directory and contain no published runtime database or application secret.

## Hosted publication verification

The new [public repository](https://github.com/guxinyihan/teamflow-kanban) received the preserved master history. [Push run 37181772257](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37181772257) completed successfully at `2026-10-04T06:07:28Z` for implementation source `3a14fa8a33331cd99424acdfaa9d34d4c193492c`. The actual job states, steps and logs were inspected; no CI correction was required.

| Actual hosted job | Runtime and result |
| --- | --- |
| `backend-sqlite (3.12)` | CPython 3.12.14; **99 passed**, 21 known warnings, 71.08 seconds; Ruff and fresh Alembic upgrade/check passed |
| `backend-sqlite (3.13)` | CPython 3.13.15; **99 passed**, 21 known warnings, 54.14 seconds; Ruff and fresh Alembic upgrade/check passed |
| `backend-postgres` | CPython 3.12.14 and actual PostgreSQL 17.11 service; **99 passed**, one known warning, 83.90 seconds |
| `frontend` | Node 24.21.0; clean `npm ci`, lint, **26 tests**, TypeScript/Vite production build passed |

These are hosted execution results, distinct from the local suite timings above. The sanitized [publication record](publication.json) contains the run, commit and job URLs. GitHub also confirmed the unchanged LICENSE blob and eight commits ahead of the upstream baseline, zero behind. The release report and documentation are added after this successful implementation run; the report identifies the validated implementation snapshot without claiming that it contains its own future commit.

Runner annotations include the existing action majors' Node 20 deprecation (GitHub ran them on Node 24) and an upcoming `ubuntu-latest` image transition. All jobs succeeded despite these maintenance notices. Browser acceptance, npm advisory audit and local PostgreSQL fresh CLI checks are additional local evidence, rather than extra hosted jobs.
