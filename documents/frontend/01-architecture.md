# Frontend — Architecture

Angular 22 SPA replacing the 22 Jinja templates. Fully standalone architecture:
no `NgModule` anywhere.

- **Root:** `frontend/`
- **Entry:** `src/main.ts` → `bootstrapApplication(App, appConfig)`

---

## 1. Why standalone and no NgModule

Confirmed by inspection: there is **no `*.module.ts` file in the repo**. The app
bootstraps with `bootstrapApplication()` and each component declares its own
`imports` array. Angular 22 treats NgModules as legacy; every generated file
follows the standalone model.

Do not introduce an NgModule. If a third-party integration documents one, take
the standalone component and the `provideX()` provider form instead.

---

## 2. Current file tree

```
frontend/
├── angular.json                 build, test, lint targets, budgets, proxy
├── eslint.config.js             flat config, angular-eslint
├── package.json
├── proxy.conf.json              /api -> http://localhost:5000 (dev server only)
├── Dockerfile                   node build -> nginx runtime
├── nginx.conf                   SPA fallback + /api proxy
├── tsconfig.json / .app / .spec
├── public/                      static assets copied verbatim
└── src/
    ├── index.html
    ├── main.ts                  bootstrapApplication
    ├── styles.scss              global entry — @use's the partials below
    ├── styles/                  design-system layers, in load order
    │   ├── _palette.scss        raw ramps, scales, breakpoints, $singles; the only hex values
    │   ├── _breakpoints.scss    bp.below()/atleast() — emits the media queries
    │   ├── _semantic.scss       role per theme, keyed by Material's token names
    │   ├── _tokens.scss         emits --ui-* custom properties
    │   ├── _material.scss       emits --mat-sys-* from the same maps
    │   ├── _reset.scss          element normalisation
    │   ├── _elements.scss       global CSS system (h1–h6, p, caption, lists, tables)
    │   ├── _layout.scss         app shell + flow primitives
    │   └── _utilities.scss      single-purpose helpers
    ├── test-setup.ts            in-memory localStorage for jsdom
    └── app/
        ├── app.ts               root component (class name: App) — the shell
        ├── app.html             rail + top bar + outlet
        ├── app.scss             rail navigation only; structure comes from _layout.scss
        ├── app.config.ts        ApplicationConfig providers
        ├── app.routes.ts        styleguide route; every feature added here
        ├── app.spec.ts
        ├── core/
        │   ├── api/
        │   │   ├── api-base-url.ts        API_BASE_URL token + apiUrl()
        │   │   └── session.interceptor.ts cookie-session bridge
        │   └── theme/
        │       ├── theme.service.ts       data-theme + localStorage.theme
        │       └── theme.service.spec.ts
        ├── ui/                  design system — standalone, exported from index.ts
        │   ├── badge.ts   button.ts   card.ts      empty-state.ts
        │   ├── field.ts   page-header.ts  record-row.ts
        │   ├── section.ts stat.ts    index.ts
        │   └── ui.spec.ts
        └── features/
            └── styleguide/      the design system, rendered
                ├── styleguide.ts / .html / .scss
```

Naming note: the root component class is **`App`**, not `AppComponent`
(`src/app/app.ts`). Angular 22's generator drops the `Component` suffix by
default. Follow the local convention: `login-page.ts` → `LoginPage`.

---

## 3. Providers (`app.config.ts`)

```ts
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(
      routes,
      withComponentInputBinding(),
      withInMemoryScrolling({ scrollPositionRestoration: 'enabled' }),
    ),
    provideHttpClient(withInterceptors([sessionInterceptor])),
  ],
};
```

| Provider | Why it is there |
|---|---|
| `provideBrowserGlobalErrorListeners()` | Routes uncaught errors through Angular's `ErrorHandler` |
| `provideZoneChangeDetection({ eventCoalescing: true })` | Coalesces change detection bursts — worth it given the large report forms |
| `withComponentInputBinding()` | Route params and query params bind directly to component `input()` signals. **Prefer this over subscribing to `ActivatedRoute`.** |
| `withInMemoryScrolling(...)` | Restores scroll on back navigation — matters for the 1,400-line report forms |
| `provideHttpClient(withInterceptors([...]))` | Functional interceptors, no class-based interceptor boilerplate |

---

## 4. The session-cookie strategy — the key architectural decision

The backend authenticates with a **signed server-side session cookie**. The
Angular app deliberately keeps that rather than migrating to JWT.

**Same origin, therefore no CORS:**

| Environment | Who serves the app | Where `/api` goes |
|---|---|---|
| Development | Angular dev server on `:4200` | `proxy.conf.json` forwards `/api` → `http://localhost:5000` |
| Docker | nginx on `:8080` (`frontend/nginx.conf`) | proxies `/api` → `backend:5000` |

Do **not** assume Flask serves the Angular bundle. It does not — confirmed by
inspecting every route in `backend/app.py`. nginx owns serving the SPA in the
Docker setup, and the legacy Jinja UI is still served from Flask on `:5000`.

Because requests are same-origin, the session cookie is sent normally and no
`SameSite=None` / CORS preflight is needed.

**What this buys:** the entire legacy authorization model — the
`psycopg` monkeypatch, the `before_request` forced-password-change guard, and 41
inline role checks — keeps working untouched.

**What it costs:** you cannot deploy the SPA to a separate CDN origin without
either a CORS configuration or re-implementing auth. If that becomes necessary,
keep the reverse proxy; do not switch to JWT casually. See
[../backend/03-authentication.md](../backend/03-authentication.md).

---

## 5. API access

### Base URL

```ts
// src/app/core/api/api-base-url.ts
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL', {
  providedIn: 'root',
  factory: () => '/api',
});

export function apiUrl(path: string): string {
  const base = inject(API_BASE_URL);
  return `${base}/${path.replace(/^\//, '')}`;
}
```

Override in tests or staging by providing `API_BASE_URL` — do not hardcode URLs.

### Interceptor

`core/api/session.interceptor.ts` handles three things:

1. **`withCredentials` + `X-Requested-With: XMLHttpRequest`.** The header lets the
   backend distinguish XHR from a browser navigation and return `401` JSON rather
   than a `302` to `/login`.
2. **Silent redirect detection.** When an unauthenticated XHR hits a protected
   route, Flask's guard answers `302 → /login`. XHR follows transparently, so the
   caller receives `200` with an **HTML login page**. The interceptor treats an
   HTML response to a JSON request as an expired session.
3. **Return URL preservation.** Redirects to `/login?returnUrl=<attempted>`.

Loop guard: if `router.url` already starts with `/login`, it does nothing.

### ⚠ The interceptor cannot protect itself

Flask currently **does not** branch on `X-Requested-With` — it always redirects.
Item 1 is the client's half of a contract whose server half is unimplemented.
Until then, detection relies entirely on sniffing `content-type: text/html`.

**Add to the backend:** in `before_request`, if the request carries
`X-Requested-With: XMLHttpRequest` and the session check fails, return
`jsonify({'error': 'unauthorized'}), 401` instead of a redirect. See
[../backend/02-routing-contract.md](../backend/02-routing-contract.md).

### `apiUrl()` vs plain strings

Use `apiUrl('worklog')`. Do not write `'/api/worklog'` — that defeats the token.

---

## 6. Routing

```ts
// src/app/app.routes.ts
export const routes: Routes = [];
```

**Empty.** Everything else is a TODO. Planned routes and their backend endpoints
are in [05-migration-plan.md](05-migration-plan.md) and
[data/screen-map.json](data/screen-map.json).

With `withComponentInputBinding()`, a route like

```ts
{ path: 'worklog/:username', component: ViewEntriesPage }
```

binds `:username` straight to a component `input()` — no `ActivatedRoute`
subscription.

### Lazy loading

Load each feature with `loadComponent`:

```ts
{
  path: 'add-entry',
  loadComponent: () =>
    import('./features/employee/add-entry-page').then((m) => m.AddEntryPage),
}
```

Do not eagerly import the two 1,400-line report screens.

---

## 7. Missing backend endpoint

`GET /api/me` does not exist. The Angular shell needs it to render the navbar,
the role switcher, and the route guard.

Return the session dict verbatim:

```json
{
  "username": "darshan",
  "full_name": "Darshan S",
  "available_roles": ["Secretary", "Campus IQAC Coordinator"],
  "role": "Secretary",
  "must_change_password": false
}
```

This is exactly `session` in the Flask app, and it mirrors
[../backend/data/permissions.json](../backend/data/permissions.json) → `session_keys`.

---

## 8. What is not built yet

| Item | Status |
|---|---|
| `routes` | `/styleguide` only |
| Design system (`ui-*`) | **done** — 10 components, [03-design-system.md](03-design-system.md) |
| App shell (rail + top bar) | **done**, unpopulated |
| Feature components | none beyond the styleguide |
| `AuthService` / session state | none |
| Route guards | none |
| Toast/flash service | none |
| `GET /api/me` | backend side missing |
| CSRF token plumbing | missing |
| `ng2-charts` | **not installed** — `chart.js` alone is present |

Build order: [05-migration-plan.md](05-migration-plan.md) §4.