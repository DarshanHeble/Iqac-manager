# Frontend — Toolchain

Exact versions from `frontend/package.json`. All installed and verified working.

---

## 1. Runtime

| Tool | Version |
|---|---|
| Node | `v26.2.0` |
| npm | `11.13.0` |
| Angular CLI | `22.1.2` |

Requires Node 20.19+ or 22.12+ per Angular 22, so Node 26 is fine.

---

## 2. Dependencies

```json
"dependencies": {
  "@angular/common":       "^22.1.0",
  "@angular/compiler":     "^22.1.0",
  "@angular/core":         "^22.1.0",
  "@angular/forms":        "^22.1.0",
  "@angular/localize":     "^22.2.1",
  "@angular/platform-browser": "^22.1.0",
  "@angular/router":       "^22.1.0",
  "@angular/cdk":         "22.2.1",
  "@angular/material":    "22.2.1",
  "chart.js":             "^4.5.1",
  "rxjs":                  "~7.8.0",
  "tslib":                 "^2.3.0",
  "zone.js":               "~0.16.0"
}
```

### ⚠ `chart.js` without `ng2-charts`

`chart.js` is a dependency but **`ng2-charts` is not installed**. Chart.js has no
Angular integration on its own — it needs manual lifecycle management or a
wrapper. Decide before writing any chart code:

- **Option A** — `npm i ng2-charts`, which wraps Chart.js with a directive and
  registers the components. Least code.
- **Option B** — a thin standalone component that instantiates `Chart` in
  `afterNextRender` and destroys it in `ngOnDestroy`. No new dependency, but you
  own the lifecycle.

See [03-design-system.md](03-design-system.md) §6.

### `@angular/localize`

Pulled in by Angular Material. Add `angular localize` to `angular.json` only if
`$localize` is actually used in templates.

### Bootstrap is gone

`bootstrap`, `bootstrap-icons`, `@ng-bootstrap/ng-bootstrap`, and `@popperjs/core`
were removed. The legacy Flask templates load Bootstrap themselves from a CDN, so
the Angular app never needed it globally — and removing it deletes the
`data-bs-theme` ambiguity described in
[03-design-system.md](03-design-system.md) §2.

If a ported screen seems to need a Bootstrap class, it needs a `ui-*` component
instead. Adding the packages back is a regression.

---

## 3. Dev dependencies

```json
"@angular/build":       "^22.1.2",
"@angular/cli":         "^22.1.2",
"@angular/compiler-cli": "^22.1.0",
"@eslint/js":           "^10.0.1",
"angular-eslint":       "22.5.0",
"eslint":               "^10.9.1",
"eslint-config-prettier":"^10.1.8",
"jsdom":                "^28.0.0",
"prettier":             "^3.8.1",
"typescript":           "~6.0.2",
"typescript-eslint":    "8.69.0",
"vitest":               "^4.0.8"
```

Note **Vitest**, not Karma or Jest — Angular 22's default unit-test runner, using
`jsdom` as the environment.

### ⚠ TypeScript `~6.0.2`

TypeScript 6 with `typescript-eslint` 8.69 and `angular-eslint` 22.5. If you hit
an unexplained type error, suspect the compiler version before suspecting your
code.

---

## 4. Scripts

```bash
npm start           # ng serve
npm run build       # ng build
npm run watch       # ng build --watch --configuration development
npm test            # ng test
npm run lint        # ng lint
npm run format      # prettier --write "src/**/*.{ts,html,scss}"
npm run format:check
```

The dev server proxies `/api` to Flask automatically — see `proxy.conf.json`,
referenced from `angular.json`.

---

## 5. TypeScript configuration

Strict mode is on. Relevant flags and their consequences:

| Flag | Consequence |
|---|---|
| `strict` | No implicit `any`, strict null checks, no implicit `this` |
| `strictTemplates` | Template type checking — **the most common source of build failures** |
| `noImplicitOverride` | Must write `override` when overriding a base member |
| `noPropertyAccessFromIndexSignature` | Must use `obj['key']` for index signatures |
| `noImplicitReturns` | All code paths must return |
| `noFallthroughCasesInSwitch` | No silent fallthrough |
| `isolatedModules` | `export type` needed for type-only re-exports |
| `verbatimModuleSyntax` | `import type` for type-only imports |

**`noPropertyAccessFromIndexSignature`** is the one that surprises people:
`response['user']` rather than `response.user` when the type has an index
signature.

---

## 6. Lint and format

- **ESLint 10 flat config** (`eslint.config.js`), no `.eslintrc`.
- **angular-eslint 22.5** — includes the template rules. `inline-template` and
  `no-any` are the ones that bite.
- **eslint-config-prettier** is applied last, so formatting conflicts do not
  double-report. Prettier and ESLint must never fight: let Prettier own
  formatting, let ESLint own correctness.

Run `npm run format` before `npm run lint` to separate real issues from style
noise.

---

## 7. `angular.json` essentials

| Setting | Value / note |
|---|---|
| Output path | `dist/frontend` |
| Builder | `@angular/build:application` (esbuild-based) |
| Styles | `src/styles.scss` only — it `@use`s the partials in `src/styles/` |
| `stylePreprocessorOptions.includePaths` | `["src/styles"]`, so a component stylesheet can write `@use 'typography' as type;` |
| Assets | `public/` copied verbatim; `src/favicon.ico`, `src/assets/` |
| Polyfills | `zone.js` |
| Dev proxy | `proxy.conf.json` |
| Default project | `frontend` |

### Bundle budgets

| Budget | Limit | Type |
|---|---|---|
| `initial` | 500 kB warning / 1 MB error | bundle |
| `anyComponentStyle` | 4 kB warning / 8 kB error | component stylesheet |

The `anyComponentStyle` budget is the one to watch. The legacy inline `<style>`
blocks run 100–200 lines per screen; porting them **verbatim into a component
`styles` array** will breach the 4 kB warning. Move shared rules to
`src/styles/` and let components stay small. This is a deliberate design
pressure — do not raise the budget to make the error go away.

Chart.js is heavy. A single chart page will likely exceed the 500 kB initial
budget, so **lazy load** chart routes.

---

## 8. Verified working

| Check | Result |
|---|---|
| `npm run build` | passes |
| `npm run lint` | passes |
| `npm run format` | passes, no changes needed |
| `ng test` | 32 passed / 32, 3 files |
| `ng serve` serves the app | passes |
| Docker build of the same app | passes — `frontend/Dockerfile`, node 24 → nginx |
| No `NgModule` in the repo | confirmed |

Re-run `npm run build && npm run lint` after any dependency change.

The image build uses `node:24-alpine` (Angular 22 accepts `^20.19 || ^22.12 ||
>=24`), which is not the Node 26 on this machine. That is deliberate — 24 is an
LTS line, so the container does not track whatever the host happens to have.
If a future dependency needs a newer Node, the image is the only place to change.

### ⚠ `/api` reaches Flask, but nothing answers there

Verified 2026-10-05 against the running stack: nginx proxies `/api` correctly
(Flask's own 404 comes back, not nginx's), but `app.py` defines **no** routes
under `/api` and contains **no** `jsonify` calls. Every legacy route is HTML or
a redirect.

So "the proxy reaches Flask" is true and also nearly meaningless on its own: it
proves the plumbing, not that an endpoint exists. Do not read a passing
`/api/healthcheck` curl as backend readiness. The full probe is in
[05-migration-plan.md](05-migration-plan.md) §5.1.

Also note `proxy.conf.json` is for `ng serve` only. Under Docker there is no dev
server; `frontend/nginx.conf` does the proxying instead.