# Release review record

Review date: 2026-10-04, Asia/Shanghai. Scope: TeamFlow changes from upstream `a41a00515b77e3ef61cfe4a7a0b3889c497e44b0`, including the current working tree. An independent read-only reviewer examined authorization, SQL transaction/order behavior, invitations, private files, WebSocket eligibility, frontend session lifecycle and legacy migrations.

## Confirmed findings and corrections

| Finding | Reproduction | Correction |
| --- | --- | --- |
| Assignment eligibility after permission changes | Restrict a team-visible board to private, or demote a team admin who lacks explicit private-board membership. The former assignee lost board access while remaining assigned. | Under existing board locks, flush the changed policy, clear ineligible canonical/legacy assignment relationships, increment task versions and record assignment activity in the same transaction. Independent API re-execution verified the clear and persisted relationship state. |
| Private legacy assignment backfill | Remove a legacy task assignee's explicit private-board membership, retain ordinary team membership, then run the official upgrade wrapper. The upgraded assignee could not work on the board. | Derive the canonical assignee from team owner/admin or an explicit board member for private boards; choose deterministically. Preserve original legacy assignment links during migration. |
| Legacy label naming collision | Seed duplicate names together with a user-created name matching the generated `[legacy ID]` suffix. Migration failed its new unique label constraint. | Retry deterministic suffixes until the board-scoped normalized name is unused; preserve every label/link. |
| Delayed unauthorized response across sessions | Dispatch a request with an old token, log out and authenticate again, then resolve the old request with 401. The new session was ended. | Match the response to its dispatched session before ending the current session; add a delayed-response regression. |

The reviewer also identified coverage gaps: exact task ID ordering, successful moves within/out of a full WIP column, and explicit role cases for team settings, board settings, columns and activity. Those checks were added in the final regression expansion. Targeted independent re-execution passed five assignment/migration cases and both delayed/current-session HTTP 401 cases. The final complete backend suites each passed 99 tests on SQLite and PostgreSQL; the frontend passed 26 tests, lint and build, and all 12 local browser checks. Current execution evidence and limits are maintained in [VERIFICATION.md](VERIFICATION.md) and [MANUAL_ACCEPTANCE.md](MANUAL_ACCEPTANCE.md).

## Review limits

This is a source review with isolated reproductions, not a penetration test, external security certification or production deployment verification. No additional confirmed material defects were found in the reviewed board authorization, ordering, invitation, private-file and channel-isolation paths. Fresh complete test results are required after corrections. GitHub publication and hosted Actions execution must be verified separately; local results cannot establish either.
