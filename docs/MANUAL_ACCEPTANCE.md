# Browser acceptance

The release browser run passed on **2026-10-04 (Asia/Shanghai)** with installed Chrome and Playwright, a real FastAPI server, and a disposable SQLite database. Four independent browser contexts exercised an owner, a member, an unrelated outsider, and a newly registered invitee. The automated report is [browser-acceptance.json](browser-acceptance.json). These are local results; they do not assert a deployed service or a hosted CI run.

The final run used Chrome 154.0.8037.93 and Playwright 1.63.0 with the upgraded frontend lockfile. It completed at **11:46:39 on 2026-10-04 (Asia/Shanghai)**: 12 checks passed, zero page errors were recorded, and the eight screenshots below were refreshed and visually inspected.

## Reproduce the browser run

Use a disposable database and upload directory. The seeder creates fake accounts, teams, tasks, invitations, and a text attachment through the API. The acceptance runner then moves tasks, adds resource records, and invites another fake account. It never saves bearer tokens in its seed file or report.

1. Follow the README installation steps. Run Alembic and the API with a fresh `DATABASE_URL`, an explicit `UPLOAD_DIR`, a generated `JWT_SECRET`, and `FRONTEND_ORIGINS=http://127.0.0.1:5173`. Start Uvicorn at `127.0.0.1:8000` with one worker.
2. In another terminal, run the frontend at `127.0.0.1:5173`; set `VITE_API_URL=http://127.0.0.1:8000/api` using [frontend/.env.example](../frontend/.env.example) or the environment.
3. Install frontend dependencies with `npm ci`. The runner uses installed Google Chrome; alternatively set `TEAMFLOW_CHROME_PATH` to an existing Chrome executable. No browser is downloaded by these scripts.
4. From `frontend/`, execute the following PowerShell commands:

```powershell
$env:TEAMFLOW_ALLOW_DISPOSABLE_SEED = 'yes'
$env:TEAMFLOW_SEED_PATH = Join-Path (Get-Location) 'test-results/seed.json'
$env:TEAMFLOW_EVIDENCE_PATH = Join-Path (Get-Location) 'test-results/browser-acceptance.json'
npm run seed:e2e
npm run test:e2e
```

`seed:e2e` generates unique usernames for each run, leaving the outsider outside the project team. The fake password is `TeamFlow-Demo-42!`. `test:e2e` can also rerun against the same seed: it resets the four seeded task positions and removes its earlier comment/checklist/label additions before checking again. Generated seeds and reports in `test-results/` are ignored by Git.

The defaults are `TEAMFLOW_API_URL=http://127.0.0.1:8000/api` and `TEAMFLOW_FRONTEND_URL=http://127.0.0.1:5173`. `TEAMFLOW_SCREENSHOT_DIR` overrides the default `docs/screenshots/` output. Run the commands from `frontend/` so the relative screenshot default resolves correctly. A browser failure exits nonzero and writes a failure report when `TEAMFLOW_EVIDENCE_PATH` is set.

## Observed checks and manual walkthrough

| Step                                                                            | Expected behavior                                                                                                             | Recorded result |
| ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Sign in as owner, member, and outsider in separate contexts                     | Each has an independent authenticated session                                                                                 | PASS            |
| Owner drags Requirements Specification from Todo to In Progress                 | HTTP 200; member receives `task.moved` and sees the same placement without reload                                             | PASS            |
| Focus Database Schema's drag handle; press Space, ArrowRight, Space             | The drag-and-drop library commits a keyboard move to In Progress                                                              | PASS            |
| Move a third task to the column with WIP limit 2 using its column selector      | HTTP 409; rollback notice; task returns to Todo and active count stays 2                                                      | PASS            |
| Open task details and download requirements.txt                                 | Existing assignee, checklist, label, and comment render; the authenticated download has the expected filename and exact bytes | PASS            |
| Add a comment, add and toggle a checklist item, add a label                     | Real API responses persist the changes and the UI displays them                                                               | PASS            |
| Open Activity                                                                   | Real committed move/comment/checklist/label records appear                                                                    | PASS            |
| Outsider uses Open shared board with the project ID and requests its attachment | Board is denied without cached private cards; attachment download returns HTTP 403                                            | PASS            |
| Owner creates an invitation for a fresh registered guest; guest accepts it      | Invitation is created and acceptance opens the team board                                                                     | PASS            |
| Inspect 1440px desktop, 768px tablet, and 390px mobile layouts                  | The board scrolls horizontally inside its container; the page and task dialog do not overflow the document width              | PASS            |
| Log the member out                                                              | Workspace clears; localStorage and sessionStorage are empty                                                                   | PASS            |
| Finish the run                                                                  | No uncaught JavaScript page errors                                                                                            | PASS            |

This browser run uses actual pointer dragging, keyboard dragging, and the accessible column selector. The frontend unit suite separately covers stale revision rollback, newer WebSocket snapshots winning over late move responses, delayed mutation completion after logout, reconnect/refetch, role-dependent controls, invitation errors, and a late HTTP 401 from an old session leaving a new session signed in.

## Screenshot evidence

All screenshots are real browser captures of fake project data, taken during the recorded run. The invitation link is deliberately redacted with a neutral gray mask; no bearer token or live invitation secret is published.

| Screenshot                                                               | Visible workflow                                                                            |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| [board.png](screenshots/board.png)                                       | Five columns, assignment, priority, due date, labels and resource counts                    |
| [wip-conflict.png](screenshots/wip-conflict.png)                         | Full In Progress column, rejected move notice, and rolled-back Todo card                    |
| [task-details.png](screenshots/task-details.png)                         | Task form, assignment, checklist and labels; remaining resources are available by scrolling |
| [activity.png](screenshots/activity.png)                                 | Activity records from actual mutations                                                      |
| [team-members-invitations.png](screenshots/team-members-invitations.png) | Roles and a newly created invitation with its secret redacted                               |
| [tablet.png](screenshots/tablet.png)                                     | Tablet board layout                                                                         |
| [mobile.png](screenshots/mobile.png)                                     | Mobile board with intentional horizontal column scrolling                                   |
| [mobile-task-details.png](screenshots/mobile-task-details.png)           | Mobile task dialog                                                                          |
