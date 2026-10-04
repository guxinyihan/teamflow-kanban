# Verified upstream baseline

The baseline used unchanged upstream commit `a41a00515b77e3ef61cfe4a7a0b3889c497e44b0`. All probes used disposable workspace databases and isolated dependencies, before TeamFlow implementation. README statements were checked separately in [UPSTREAM_CLAIMS_AUDIT.md](UPSTREAM_CLAIMS_AUDIT.md).

## Backend

Python 3.12.15 ran the original FastAPI 0.104.1, SQLAlchemy 2.0.23, Pydantic 2.5.1, Passlib 1.7.4 and python-jose 3.3.0 pins in a separate virtual environment. The probe additionally used bcrypt 4.0.1 for legacy Passlib compatibility, HTTPX 0.27.2 for TestClient and Alembic 1.17.2. These compatibility packages are test setup changes, not upstream implementation changes.

The original `app.main` imported successfully and `/openapi.json` returned 200. No inherited automated test suite was present. Startup created eleven ORM tables rather than applying a functional Alembic chain.

| Disposable multi-user probe | Observed result |
| --- | --- |
| Anonymous reads of a private task's labels, comments and attachments | Each returned HTTP 200 |
| Anonymous checklist insertion into the private task | HTTP 500, but the inserted checklist item remained committed |
| Unrelated authenticated account creates task on `is_public=True` board | HTTP 500, but the unauthorized task remained committed |
| Actual WebSocket route | Absent |

The last two results were confirmed directly against the disposable SQLite database after the responses: the private task retained `Unauthorized write` in its checklist, and a second task named `Unauthorized write` belonged to the unrelated account on the other board. A 500 response did not prevent either mutation. The baseline probe suppressed upstream debug logging so credentials were not emitted during this verification.

Commands used the isolated runtime and environment:

```powershell
uv venv work/backend-baseline-venv --python work/python/cpython-3.12.15-windows-x86_64-none/python.exe
uv pip install --python work/backend-baseline-venv/Scripts/python.exe -r outputs/teamflow-kanban/requirements.txt
uv pip install --python work/backend-baseline-venv/Scripts/python.exe bcrypt==4.0.1 httpx==0.27.2 alembic==1.17.2
work/backend-baseline-venv/Scripts/python.exe work/baseline_probe.py
```

`requirements.txt` in the install command refers to its unchanged upstream contents at baseline time. The final project has a different, tested dependency manifest. `baseline_probe.py` and its disposable database are scratch verification artifacts, not released application files.

## Frontend

Node 24.18.0 and npm 11.16.0 installed the untouched upstream frontend with a workspace-only npm cache. React 18.3.1, TypeScript 5.6, Vite 6 and `@hello-pangea/dnd` 17 were inherited. The actual drag-and-drop library is hello-pangea/dnd. React Query 5 was present as a dependency but was not wired into application queries.

| Command | Actual result |
| --- | --- |
| `npm ci --no-audit --no-fund` | Exit 0; 384 packages installed |
| `npm run build` | Exit 1; `NewTaskModal.tsx(10,80)` TS6133: unused `status` |
| `npm run lint` | Exit 1; 8 errors and 3 warnings |

The lint errors concerned unused variables/props and explicit `any` declarations; warnings concerned effect dependencies and mixed component exports. The first install attempt failed because the default npm cache was outside the writable workspace; setting an isolated cache resolved it.

Observed frontend gaps included shared localStorage board/task state, local column configuration disconnected from rendered columns, sequential positional PUTs during drag-and-drop, placeholder assignment controls, public attachment URLs, and no invitation, activity or WebSocket workflow. There were no frontend tests. Useful inherited forms, Axios access, task dialogs, cards, metadata and subresource workflows were retained and adapted in TeamFlow.
