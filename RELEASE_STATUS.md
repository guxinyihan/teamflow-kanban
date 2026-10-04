# Release status

Updated: 2026-10-04, Asia/Shanghai.

**Local implementation, review and verification are complete. Publication is waiting for GitHub authentication.** No new public repository has been created, no project push has occurred, and hosted GitHub Actions have not run for TeamFlow.

The original remote is retained as `upstream`; `origin` will point to the new repository after creation.

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

The browser exercise includes pointer/keyboard moves, two-session WebSocket synchronization, HTTP 409 WIP rejection and UI rollback, protected file download, outsider denial, real invitation acceptance, task subresources/activity and logout cleanup. The database suites additionally verify guessed IDs, owner invariants, concurrent ordering/final-slot contention, rollback without success events, token validation and populated legacy backfills.

## Publication blocker

`gh auth status` currently reports an invalid credential for the active GitHub account. A noninteractive check also found no usable native Git credential. The connected GitHub app can inspect the authenticated account, but its available tools do not create repositories or provide credentials to native Git.

Complete authentication in your own terminal:

```powershell
gh auth login -h github.com
```

Use the account intended to own the public repository. Keep passwords, bearer tokens and authorization codes out of chat. After login, the remaining authorized work is to verify the active account, select a new unused repository name, create the public repository, push the preserved master history, inspect actual hosted Actions, correct any failures and create `FINAL_REPORT.md` with the confirmed repository URL and hosted results.

The preferred repository name is `teamflow-kanban`; an existing repository will not be overwritten. A safe unused variant such as `teamflow-kanban-enhanced` will be selected when necessary.

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

Documentation and screenshot evidence accompany these milestones in the following documentation commit. History was retained rather than replaced with a new initial commit.

## Deployment limits

The current WebSocket transport requires one application instance/worker. Sessions use access tokens with explicit re-login, and invitation delivery uses copyable links. Chrome browser acceptance is local-only; Python 3.13 is configured for hosted CI but has not been locally executed. SQLite expression-index reflection and Starlette TestClient warnings are documented. Full setup commands and the remaining product limitations are in [README.md](README.md).
