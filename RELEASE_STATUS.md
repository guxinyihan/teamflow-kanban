# Release status

Updated: 2026-10-04, Asia/Shanghai.

**Implementation, independent review, local verification and public repository publication are complete. All four actual hosted GitHub Actions jobs passed for the published implementation.**

The new public repository is [guxinyihan/teamflow-kanban](https://github.com/guxinyihan/teamflow-kanban). `origin` points there; the original remote is retained as `upstream`. [FINAL_REPORT.md](FINAL_REPORT.md) records all 42 requested release items.

## Verified local gates

| Gate | Evidence |
| --- | --- |
| Full upstream master history and MIT attribution | Upstream `a41a00515b77e3ef61cfe4a7a0b3889c497e44b0` remains an ancestor; clone is not shallow; LICENSE Git blob matches upstream exactly |
| Claims/source audit and isolated baseline | [Claims audit](docs/UPSTREAM_CLAIMS_AUDIT.md), [baseline](docs/BASELINE.md), [development plan](DEVELOPMENT_PLAN.md) |
| SQLite and real PostgreSQL authorization/domain/integration suites | **99 passed on each engine**; [verification](docs/VERIFICATION.md) |
| Fresh/legacy migrations and original data protection | CLI checks passed on both engines; copied real upstream database upgraded with backup and original baseline hash unchanged |
| Backend lint | Ruff passed |
| Frontend clean install, unit tests, lint and production build | `npm ci` passed; **26 tests passed**; lint/build passed |
| Frontend lockfile advisory audit | Zero reported vulnerabilities after remediation; [dependency record](docs/DEPENDENCIES.md) |
| Real multi-user browser acceptance | **12 checks passed**, zero page exceptions; [acceptance](docs/MANUAL_ACCEPTANCE.md), [sanitized report](docs/browser-acceptance.json) |
| Real screenshots | Eight fake-data browser captures refreshed and inspected |
| Independent review | Confirmed permission/assignment, legacy migration and delayed-session defects corrected; [review record](docs/RELEASE_REVIEW.md) |
| Source hygiene | Whitespace check passed; no runtime databases/uploads, environment secrets, dependencies or generated builds tracked; local Markdown links resolve |
| Public repository and actual hosted CI | New public repository created and full master pushed; [run 37181772257](https://github.com/guxinyihan/teamflow-kanban/actions/runs/37181772257) passed all four jobs |

The browser exercise includes pointer/keyboard moves, two-session WebSocket synchronization, HTTP 409 WIP rejection and UI rollback, protected file download, outsider denial, real invitation acceptance, task subresources/activity and logout cleanup. The database suites additionally verify guessed IDs, owner invariants, concurrent ordering/final-slot contention, rollback without success events, token validation and populated legacy backfills.

## Confirmed publication

The authenticated account was verified as `guxinyihan`. The preferred name was unused, so a new public `teamflow-kanban` repository was created without overwriting an existing project. The repository has the requested description and ten topics. GitHub's master ref matched local implementation `3a14fa8a33331cd99424acdfaa9d34d4c193492c`; its LICENSE blob matched the original, and the upstream baseline remained an ancestor.

The actual push-triggered workflow completed successfully at `2026-10-04T06:07:28Z`. SQLite/Python 3.12, SQLite/Python 3.13 and PostgreSQL 17 each passed 99 backend tests. Both SQLite jobs passed fresh Alembic upgrade/check. The Node 24 job passed 26 frontend tests, lint and production build. No hosted CI fix was needed. [Publication evidence](docs/publication.json) records the inspected source snapshot and job URLs.

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

The release report and publication evidence accompany these milestones in the final documentation commit. History was retained rather than replaced with a new initial commit.

## Deployment limits

The current WebSocket transport requires one application instance/worker. Sessions use access tokens with explicit re-login, and invitation delivery uses copyable links. Chrome browser acceptance is local-only; Python 3.13 passed hosted CI and was not locally executed. SQLite expression-index reflection, Starlette TestClient and runner maintenance notices are documented. Full setup commands and the remaining product limitations are in [README.md](README.md).
