# Frontend dependency verification

The full frontend lockfile audit on **2026-10-04 (Asia/Shanghai)** returned **zero reported vulnerabilities** after the updates below. The release uses `npm ci` and the committed `package-lock.json`; this is an observed registry audit result for that dependency snapshot.

The final clean install added 419 packages and exited successfully. Against that exact installed lockfile, all 26 unit tests in four files passed; ESLint and the TypeScript/Vite production build also exited successfully. The refreshed Chrome acceptance run passed all 12 checks with no uncaught page errors, and all eight screenshots were visually inspected after the Tailwind migration. Local versions were Node 24.18.0, npm 11.16.0, and Chrome 154.0.8037.93.

| Package | Verified release version | Reason |
| --- | --- | --- |
| React / React DOM | 18.3.1 | Preserve the upstream React foundation |
| Axios | 1.20.0 | Resolve reported request construction, redirect, and multipart dependency advisories |
| Vite | 6.4.3 | Resolve the inherited development-server file-access advisories within the existing major version |
| Tailwind CSS / @tailwindcss/postcss | 4.3.3 | Replace the unpatched Tailwind 3 glob/watcher dependency chain |
| Vitest | 4.1.11 | Use the patched v4 mocker release while retaining Vite 6 and the existing test design |

The initial complete audit reported 38 vulnerable packages, including the critical transitive `form-data` package. That critical package belongs to Axios's Node adapter; the browser UI uses native browser FormData. Compatible updates with `npm audit fix` reduced the report to eight build/test packages. Targeted Tailwind and Vitest upgrades removed the remaining reports. No `--force`, dependency overrides, or global package-script approvals were used.

The Tailwind migration uses the official PostCSS package, imports Tailwind from CSS, and loads the retained JavaScript configuration explicitly. The auth form shadow and focus-outline utilities use their v4 equivalents. Application component styles and the React drag-and-drop structure remain adapted from the upstream project. Tailwind 4 targets Safari 16.4+, Chrome 111+, and Firefox 128+; the actual release browser run uses installed Chrome. These configuration and compatibility decisions follow the [official Tailwind upgrade guide](https://tailwindcss.com/docs/upgrade-guide).

Vitest 4.1.11 includes a backported restriction on redirect mocks to the filesystem allowlist, as recorded in the [official v4.1.11 release notes](https://github.com/vitest-dev/vitest/releases/tag/v4.1.11). Its published Node engine supports Node 20, 22, and 24; local verification uses Node 24. The project uses jsdom unit tests and a separate Playwright API/browser acceptance runner.

Recheck the exact installed dependency snapshot from `frontend/`:

```powershell
npm ci
npm audit
npm test
npm run lint
npm run build
```

For environments that restrict the default npm cache directory, set `npm_config_cache` to a writable workspace directory. The local release verification used that setting without changing user-level npm configuration. Reproduce the real API/browser run using [MANUAL_ACCEPTANCE.md](MANUAL_ACCEPTANCE.md); its screenshots were refreshed after the CSS pipeline migration.
