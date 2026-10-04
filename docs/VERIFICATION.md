# Verification evidence

Verified on **2026-10-04, Asia/Shanghai**, using isolated workspace runtimes and disposable databases. Current complete suites and the browser rerun verify corrected source `09b99551ea2545298a2ce5d279b7bd7c401a6d99`; unchanged frontend, migration CLI and screenshot evidence is identified separately. The local results below are followed by inspected hosted GitHub Actions results.

## Backend release checks

| Check | Actual result |
| --- | --- |
| Complete current SQLite backend suite | **100 passed**, 21 known warnings, exit 0, 76.32 seconds |
| Same current suite on PostgreSQL 17.11 | **100 passed**, one known warning, exit 0, 118.35 seconds |
| `python -m ruff check backend` | Passed, exit 0 |
| Fresh SQLite `alembic upgrade head` and `alembic check` | Earlier separate local CLI check passed; current hosted jobs also passed; migration source unchanged |
| Fresh PostgreSQL `alembic upgrade head` and `alembic check` | Earlier separate local CLI check passed; current full suite includes fresh migrations; migration source unchanged |
| Legacy CLI preflight and upgrade of a copy of the actual upstream baseline database | Earlier separate CLI check passed with automatic SQLite backup and unchanged original; current full suite also covers populated migrations |
| CI workflow YAML parsing and locked-install configuration | Passed |
| Installed dependency compatibility and exact lock comparison | `pip check` passed; all 45 installed packages match `requirements-dev.lock`; direct AnyIO declaration added no installed package |

The suite timings above are reported by pytest. Current measured process wall times were 81.359 seconds for SQLite and 125.33 seconds for PostgreSQL. Both final 100-test runs used the same source and test tree.

The final fixture uses `autoflush=False` and `expire_on_commit=False`, matching the production session configuration. The full SQLite/PostgreSQL runs above happened after that parity change. Tests use the production Alembic chain rather than ORM `create_all()`. SQLite tests receive separate temporary files; PostgreSQL tests receive separate generated schemas inside a disposable test database and remove only those schemas afterward.

The suite includes role and guessed-ID authorization, owner transfer and removal invariants, public-read write denial, invitation expiry/revocation/replay/wrong-account checks, column/WIP rules, concurrent moves and final-slot WIP contention, stale revisions, archive/assignment/subresource behavior, private attachment validation and cleanup, legacy attachment import, board/team deletion cascades, committed activity and WebSocket events, channel isolation, cancellation-safe finalization, expired identities, revoked membership, injected commit failure rollback, case-insensitive account uniqueness, and fresh/populated legacy migrations.

Focused authentication checks exercise the HTTP boundary with expired and future-issued identities, missing required claims, wrong issuer/audience/type, unknown accounts, invalid signatures, unsigned tokens and disallowed algorithms. Legacy bcrypt login retains the upstream 72-byte compatibility for the successful login, then upgrades to Argon2 bound to the full password. New passwords distinguish suffixes beyond 72 bytes; malformed stored hashes return 401 without changing the account.

Ordering assertions compare exact task IDs after moves up, down and between populated columns, including source/destination order and absence of loss or duplication. A full WIP column permits reordering and moving work out; an incoming task is admitted only after a slot is freed. The role matrix exercises owner/admin/member/outsider against team settings, board settings, column create/update/delete and WIP, task create/update/delete and activity reads under team/private/public-read visibility.

Assignment lifecycle checks cover active and archived work when visibility changes, role demotion across multiple boards, and preservation of assignments that retain team or explicit board edit access. Legacy migrations choose only eligible private-board assignees while retaining original multi-assignee links, and preserve duplicate labels even when a generated disambiguation name already exists.

Release checks found and corrected timezone-aware invite expiry conversion, duplicate association deletes from loaded child collections, assignment cleanup after visibility/role changes, private-board legacy assignee selection, and repeated legacy label-name collisions. Injecting a real session commit failure verifies that no task, activity row, revision increment or successful WebSocket event survives the failed transaction.

The new label-collision regression initially failed on PostgreSQL because its fixture manually assigned an ID without advancing the serial sequence. The fixture now inserts through the upstream auto-generated ID mechanism and retains every collision/link assertion. The initial 99-test suite passed both engines after that fixture correction; the final suite now contains 100 tests after the separately verified WebSocket shutdown regression below.

## WebSocket shutdown correction

The initial hosted implementation passed, but the subsequent documentation workflow exposed Python 3.13 WebSocket context teardown raising `CancelledError` after its body assertions completed (98 passed/one failed). An independent deterministic regression reproduced cancellation interrupting the final awaited child-task drain, failed against the old implementation and passed against `09b9955`. Finalization now shields only that drain with `anyio.CancelScope(shield=True)` and retains parent cancellation propagation, following [AnyIO's finalization guidance](https://anyio.readthedocs.io/en/stable/cancellation.html#finalization). No broad cancellation catch or test skip was added. AnyIO is directly declared in runtime requirements; its existing locked version remains 4.15.1 and the installed environment remains 45 packages.

## Reproduction commands

Run from the repository root after installing the tested development lock in an isolated virtual environment:

```powershell
python -m pip install -r requirements-dev.lock
python -m pip check
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

The released frontend snapshot was clean-installed and verified on **2026-10-04, Asia/Shanghai**, after dependency remediation and the Tailwind 4 migration. Frontend source and lockfile are unchanged by the backend shutdown correction; the corrected hosted frontend job reran clean installation, tests, lint and build successfully.

| Check | Actual result |
| --- | --- |
| `npm ci` from committed lockfile | Passed, exit 0; 419 packages installed |
| `npm audit --json` | Passed, exit 0; zero reported vulnerabilities at every severity |
| `npm test` | **26 passed** across four files, exit 0; Vitest 4.1.11 |
| `npm run lint` | Passed, exit 0 |
| `npm run build` | Passed, exit 0; TypeScript and Vite 6.4.3, 652 modules |
| Latest real Chrome/Playwright acceptance against corrected backend | **12 checks passed**, zero uncaught page errors, exit 0; 14:38:58 Asia/Shanghai |
| Published application screenshots | Eight from the earlier 11:46 run, refreshed after the CSS pipeline update and visually inspected |

The unchanged frontend build produced an initial JavaScript chunk of 332.91 kB (105.30 kB gzip), a lazy board chunk of 212.05 kB (65.28 kB gzip), and 22.24 kB CSS (6.01 kB gzip). These are build artifact sizes, not measured user-performance scores. The latest browser run used Chrome 154.0.8037.93 with Playwright 1.63.0 and completed at `2026-10-04T06:38:58.595Z` (14:38:58 Asia/Shanghai), verifying corrected backend source. Its eight new captures stayed under the isolated workspace's `work/` directory and are not published or claimed as visually inspected. Published screenshots still belong to the earlier `2026-10-04T03:46:39.825Z` (11:46:39) run.

Frontend regressions exercise role-aware controls, stale/WIP move rollback, exact optimistic ordering, newer snapshots winning over late responses, mutation completion after logout, the delayed old-session HTTP 401 race, WebSocket reconnect/refetch, invitations, private download and human-readable activity details. The browser run observes real `task.moved` frames and HTTP 409 responses, actual pointer/keyboard dragging, correct download bytes, outsider denial, matching-account invitation acceptance and empty browser storage after logout.

The dependency audit is an observed registry result for the unchanged released lockfile, not a guarantee against future advisories. See [DEPENDENCIES.md](DEPENDENCIES.md), [MANUAL_ACCEPTANCE.md](MANUAL_ACCEPTANCE.md), the sanitized [current browser report](browser-shutdown-acceptance.json) and [earlier screenshot-run report](browser-acceptance.json). Raw local command outputs remain in the isolated workspace's `work/` directory and contain no published runtime database or application secret.

## Hosted publication verification

The new [public repository](https://github.com/guxinyihan/teamflow-kanban) received the preserved master history. Corrected-source [push run 37183466351](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37183466351) completed successfully at `2026-10-04T06:42:52Z` for `09b99551ea2545298a2ce5d279b7bd7c401a6d99`. Actual job states, steps and logs were inspected after the cancellation fix.

| Actual hosted job | Runtime and result |
| --- | --- |
| `backend-sqlite (3.12)` | CPython 3.12.14; **100 passed**, 21 known warnings, 71.54 seconds; Ruff and fresh Alembic upgrade/check passed |
| `backend-sqlite (3.13)` | CPython 3.13.15; **100 passed**, 21 known warnings, 68.38 seconds; Ruff and fresh Alembic upgrade/check passed |
| `backend-postgres` | CPython 3.12.14 and actual PostgreSQL 17.11 service; **100 passed**, one known warning, 115.99 seconds |
| `frontend` | Node 24.21.0; clean `npm ci`, lint, **26 tests**, TypeScript/Vite production build passed |

These are hosted execution results, distinct from the local suite timings above. The sanitized [publication record](publication.json) contains the current run, commit and job URLs plus previous runs. The original LICENSE blob is unchanged, the upstream baseline remains an ancestor, and source `09b9955` is ten commits ahead of that baseline, zero behind. The release report and documentation follow this successful corrected implementation run and identify its immutable snapshot without claiming their own future commit has passed.

The earlier [initial run 37181772257](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37181772257) passed the initial 99-test implementation at `3a14fa8`. The following [documentation run 37182207962](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37182207962) failed Python 3.13 during WebSocket teardown (98 passed/one failed). Those historical results are retained rather than replaced; the current 100-test corrected run above is the release source verification.

Runner annotations include the existing action majors' Node 20 deprecation (GitHub ran them on Node 24) and an upcoming `ubuntu-latest` image transition. All jobs succeeded despite these maintenance notices. Browser acceptance, npm advisory audit and local PostgreSQL fresh CLI checks are additional local evidence, rather than extra hosted jobs.
