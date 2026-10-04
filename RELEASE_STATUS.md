# Release status

Updated: 2026-10-04, Asia/Shanghai.

**Implementation, independent review, local verification and public repository publication are complete. All four actual hosted GitHub Actions jobs passed for corrected source `09b99551ea2545298a2ce5d279b7bd7c401a6d99`.**

The new public repository is [guxinyihan/teamflow-kanban](https://github.com/guxinyihan/teamflow-kanban). `origin` points there; the original remote is retained as `upstream`. [FINAL_REPORT.md](FINAL_REPORT.md) records all 42 requested release items.

## Verified local gates

| Gate | Evidence |
| --- | --- |
| Full upstream master history and MIT attribution | Upstream `a41a00515b77e3ef61cfe4a7a0b3889c497e44b0` remains an ancestor; clone is not shallow; LICENSE Git blob matches upstream exactly |
| Claims/source audit and isolated baseline | [Claims audit](docs/UPSTREAM_CLAIMS_AUDIT.md), [baseline](docs/BASELINE.md), [development plan](DEVELOPMENT_PLAN.md) |
| SQLite and real PostgreSQL authorization/domain/integration suites | **100 passed on each engine**, including cancellation-safe WebSocket finalization; [verification](docs/VERIFICATION.md) |
| Fresh/legacy migrations and original data protection | CLI checks passed on both engines; copied real upstream database upgraded with backup and original baseline hash unchanged |
| Backend lint and installed dependency consistency | Ruff, `pip check` and all 45 exact lock comparisons passed |
| Frontend clean install, unit tests, lint and production build | `npm ci` passed; **26 tests passed**; lint/build passed |
| Frontend lockfile advisory audit | Zero reported vulnerabilities after remediation; [dependency record](docs/DEPENDENCIES.md) |
| Real multi-user browser acceptance | Corrected-backend rerun: **12 checks passed**, zero page exceptions, 14:38:58 Asia/Shanghai; [acceptance](docs/MANUAL_ACCEPTANCE.md), [current sanitized report](docs/browser-shutdown-acceptance.json) |
| Real screenshots | Eight published fake-data captures from the inspected 11:46 run; the rerun's captures stayed in the isolated workspace |
| Independent review | Confirmed permission/assignment, legacy migration and delayed-session defects corrected; [review record](docs/RELEASE_REVIEW.md) |
| Source hygiene | Whitespace check passed; no runtime databases/uploads, environment secrets, dependencies or generated builds tracked; local Markdown links resolve |
| Public repository and actual hosted CI | New public repository created and full master pushed; corrected-source [run 37183466351](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37183466351) passed all four jobs |

The browser exercise includes pointer/keyboard moves, two-session WebSocket synchronization, HTTP 409 WIP rejection and UI rollback, protected file download, outsider denial, real invitation acceptance, task subresources/activity and logout cleanup. The database suites additionally verify guessed IDs, owner invariants, concurrent ordering/final-slot contention, rollback without success events, token validation and populated legacy backfills.

## Confirmed publication

The authenticated account was verified as `guxinyihan`. The preferred name was unused, so a new public `teamflow-kanban` repository was created without overwriting an existing project. The repository has the requested description and ten topics. The pushed implementation is `09b99551ea2545298a2ce5d279b7bd7c401a6d99`; its LICENSE blob matches the original, and the upstream baseline remains an ancestor. This source contains 22 reachable commits: 12 inherited and ten TeamFlow commits.

The corrected push-triggered workflow completed successfully at `2026-10-04T06:42:52Z`. SQLite/Python 3.12, SQLite/Python 3.13 and PostgreSQL 17 each passed 100 backend tests. Both SQLite jobs passed Ruff and fresh Alembic upgrade/check. The Node 24 job passed 26 frontend tests, lint and production build. [Publication evidence](docs/publication.json) records the inspected source snapshot, job URLs and previous runs.

The initial [99-test run](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37181772257) passed. The following [documentation run](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37182207962) exposed Python 3.13 WebSocket teardown `CancelledError` (98 passed/one failed after the test body assertions completed). A deterministic failing regression reproduced async cleanup interruption; `09b9955` shields only finalization while preserving cancellation propagation. Both current local suites and all corrected hosted jobs pass 100 tests.

This publication record and final report follow the already successful implementation run. They identify that immutable validated source rather than assigning an unverified result to a future documentation commit. Public GitHub publication provides source hosting; it does not deploy the application.

## Implementation milestones

| Commit | Actual milestone |
| --- | --- |
| `3282f10` | Upstream claims audit and invariant plan |
| `a69b72d` | Board authorization and atomic movement regressions |
| `db6fd9b` | Ordering, WIP, attachment and frontend reconciliation gates |
| `14279d2` | Authorized transactional backend and migrations |
| `de6cd2e` | Assignment lifecycle reconciliation, legacy migration corrections and final backend regressions |
| `01247f3` | Locked SQLite/PostgreSQL/frontend CI configuration |
| `115c73c` | Responsive collaboration workflows, session reconciliation, patched frontend dependency snapshot and browser harness |
| `3a14fa8` | Architecture, complete local release evidence and real screenshots |
| `b6e5b8e` | Initial public publication report and first successful hosted verification record |
| `09b9955` | Cancellation-safe WebSocket finalization, deterministic regression and explicit existing AnyIO runtime dependency |

The release report and publication evidence accompany these milestones in the final documentation commit. History was retained rather than replaced with a new initial commit.

## Deployment limits

The current WebSocket transport requires one application instance/worker. Sessions use access tokens with explicit re-login, and invitation delivery uses copyable links. Chrome browser acceptance is local-only; Python 3.13 passed hosted CI and was not locally executed. SQLite expression-index reflection, Starlette TestClient and runner maintenance notices are documented. Full setup commands and the remaining product limitations are in [README.md](README.md).
