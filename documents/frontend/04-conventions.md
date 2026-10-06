# Frontend — Conventions

Follow these when adding files. They describe what the scaffold already does, so
new code matches it.

---

## 1. Standalone only

No `NgModule`. Confirm the repo has none:

```bash
find frontend/src -name "*.module.ts"     # empty
```

Every component declares its own dependencies in `imports`:

```ts
@Component({
  selector: 'app-add-entry-page',
  imports: [ReactiveFormsModule, NgbDatepicker],
  templateUrl: './add-entry-page.html',
  styleUrl: './add-entry-page.scss',
})
export class AddEntryPage {}
```

Third-party docs showing `NgbModule.forRoot()` → use the `provideX()` form.

---

## 2. File and class naming

Angular 22's generator **drops the `Component` suffix**. The root class is `App`,
not `AppComponent` (`src/app/app.ts`).

| Type | File | Class | Selector |
|---|---|---|---|
| Page (routed) | `login-page.ts` | `LoginPage` | `app-login-page` |
| Component | `category-task-field.ts` | `CategoryTaskField` | `app-category-task-field` |
| Service | `auth.service.ts` | `AuthService` | — |
| Interceptor | `session.interceptor.ts` | `sessionInterceptor` | — |
| Guard | `auth.guard.ts` | `authGuard` | — |

- Selector prefix is `app-`.
- One component per file.
- Templates are `.html`, styles `.scss` — kebab-case, matching the class
  (`login-page.html`, `login-page.scss`).

---

## 3. Folder layout

```
src/app/
├── core/                 app-wide singletons; inject here, never re-provide
│   ├── api/              apiUrl() token + session interceptor
│   ├── theme/            ThemeService — data-theme + localStorage
│   ├── guards/
│   └── models/
├── ui/                    the design system; never put business logic here
│   ├── badge.ts button.ts card.ts empty-state.ts field.ts
│   ├── page-header.ts record-row.ts section.ts stat.ts
│   └── index.ts          the only import surface
└── features/             one folder per legacy area
    ├── auth/
    ├── employee/
    ├── admin/
    ├── coordinator/
    └── secretary/
```

Rule of thumb: `core` has one instance and knows about the app; `ui` is
reusable presentation with no knowledge of IQAC business rules; `features` owns a
screen's behaviour.

There is deliberately **no `shared/` directory.** Presentation that is specific
to one feature belongs in that feature; presentation reused across features
belongs in `ui/` and gets a `ui-` prefixed selector. That distinction is the
whole point — a `ui-*` component is a promise that it works for any screen.

Import from `ui/index.ts`, never from a component file directly:

```ts
import { UiCard, UiBadge } from '../ui';   // ✓
import { UiCard } from '../ui/card';        // ✗
```

A screen reaching past the barrel is how a design system turns into a pile of
files nobody is willing to change.

---

## 4. State: signals

Angular 22 — prefer signals over `BehaviorSubject`/`subscribe`:

```ts
export class AuthService {
  private readonly userSignal = signal<SessionUser | null>(null);
  readonly user = this.userSignal.asReadonly();

  isAdmin(): boolean {
    return this.userSignal()?.role === 'Admin';
  }
}
```

- `input()` / `output()` for component boundaries, not `@Input`/`@Output`.
- `computed()` for derived state, not getters that recompute on every CD.
- `resource()` / `httpResource()` for data fetching, not hand-written
  `subscribe` blocks that need manual teardown.
- **Never `subscribe` in `ngOnInit` without a teardown.** Prefer `takeUntilDestroyed()`.

---

## 5. Routing and route params

`withComponentInputBinding()` is enabled, so params bind to inputs:

```ts
// app.routes.ts
{
  path: 'worklog/:username',
  loadComponent: () =>
    import('./features/employee/view-entries-page').then((m) => m.ViewEntriesPage),
}
```

```ts
export class ViewEntriesPage {
  readonly username = input.required<string>();   // bound from the route
}
```

Prefer this over `ActivatedRoute.paramMap.subscribe(...)`.

### Lazy loading

`loadComponent` for every feature route. Mandatory for the two 1,400-line report
screens and for any chart route — both breach the initial bundle budget eagerly.

---

## 6. API calls

```ts
import { HttpClient } from '@angular/common/http';
import { apiUrl } from '../../core/api/api-base-url';

private readonly http = inject(HttpClient);

getEntries(username: string) {
  return this.http.get<WorklogEntry[]>(apiUrl(`worklog/${username}`));
}
```

Rules:

- Always `apiUrl()`. Never hardcode `'/api/...'`.
- `inject()` rather than constructor injection.
- Type every request with an interface. Put API shapes in
  `core/models/`, named for the domain — `worklog-entry.ts`, `signed-report.ts`
  — **not** `IWorklogEntryDto` or `worklog-response.model.ts`.
- The interceptor already sets `withCredentials` and `X-Requested-With`. Do not
  repeat it.

### ⚠ Do not trust client-side role checks

The backend matches roles four different ways and does **not** patch `fetchall()`
([../backend/10-gotchas.md](../backend/10-gotchas.md) §1, §4). A guard is a UX
convenience; the server remains the only authority. Never hide a control instead
of rejecting the request server-side.

---

## 7. Types

- Define an interface for every API payload.
- Model **`reporting_month` and `date` as `string`**, not `Date`. The backend
  returns `YYYY-MM` and `YYYY-MM-DD` from `VARCHAR` columns
  ([../backend/04-data-model.md](../backend/04-data-model.md) §3). A `Date` will
  reintroduce timezone bugs for no benefit.
- Do not model `role` as a union of the five known values — `users.role` is free
  text in a `VARCHAR`. Use `string` plus `available_roles: string[]`.
- Prefer `readonly` on interface fields that the client never mutates.

---

## 8. Forms

`ReactiveFormsModule`. The largest forms here (1,424 and 1,442 legacy lines) need
typed forms and explicit validators.

- Type forms: `NonNullableFormBuilder`.
- Keep validation messages in one place per screen, shown in a
  `ValidationSummary` component.
- Server-side validation errors must map onto form controls. Do not only
  `flash()` them.

---

## 9. Errors and loading

- Centralise in an interceptor or a small `ApiErrorService`. At minimum, map
  status → user message in one place.
- **A `401` or an HTML content-type means the session expired.** The existing
  `sessionInterceptor` redirects to `/login?returnUrl=…`.
- Show a loading state for every request. The legacy screens block on form POSTs
  with no feedback.

---

## 10. Flash messages → toasts

The legacy app uses Flask `flash()`, which cannot work from an XHR API. Replace
with a `ToastService` + `ToastContainer` in the shell.

**This requires a backend change:** every endpoint that flashes on success must
also return JSON carrying the message, e.g.

```json
{ "message": "Entry saved", "level": "success" }
```

Otherwise the new client shows nothing where the legacy UI showed a flash. See
[../backend/02-routing-contract.md](../backend/02-routing-contract.md).

---

## 11. Styling: tokens only

**No component may contain a raw hex, a literal `font-size`, a magic spacing
value, or its own media query.** This is the rule the whole design system rests
on, and it is enforced mechanically by `ui/ui.spec.ts`, which fails the test run
if any component style violates it.

```scss
// ✗ hardcoded — stops responding to the theme
color: #003366;
font-size: 14px;
padding: 12px;
@media (width <= 640px) { … }

// ✓ token-driven — follows both themes automatically
color: var(--ui-primary);
@include type.text-role(caption);
padding: var(--ui-space-3);
@include bp.below(sm) { … }
```

In component stylesheets, `@use 'typography' as type;` gives you the type
mixins, and `@use 'breakpoints' as bp;` the responsive ones. Prefer them over
hand-writing the property.

A raw `@media` is banned for the same reason a raw hex is: a threshold written in
one component cannot be found, retuned, or reasoned about from any other. The
values live in `_palette.scss` (`sm` 640, `md` 768, `lg` 1024) and are emitted by
`_breakpoints.scss`.

### Which layer does this belong in?

| Change | Put it in |
|---|---|
| A new colour | `$singles` or a ramp in `src/styles/_palette.scss` |
| A new spacing, size, radius, or duration step | the scale in `src/styles/_palette.scss` |
| A new responsive threshold | `$breakpoints` in `src/styles/_palette.scss` |
| What a token means, or its value per theme | `src/styles/_semantic.scss` |
| What an element like `<p>` or `<figcaption>` means | `src/styles/_elements.scss` |
| App shell or page flow | `src/styles/_layout.scss` |
| One screen's arrangement | that feature's component styles |

If you catch yourself adding a value to three components, it belongs in the
global layer instead.

### Tone, never colour

`ui-badge`, `ui-stat`, and `ui-record-row` take `tone="success | warning | …"`,
never a colour. Tones resolve to a different foreground, background, and rule per
theme automatically; a colour would not. If a screen needs a status the four tones
do not cover, that means the status model should grow — not that a hex should be
passed in.

### Slots are attributes, not directives

Projected content is tagged with a plain attribute — `<div ui-card-actions>`,
`<span ui-record-title>`. **Do not import a marker class for these.** The wrapper
is always rendered and collapses via CSS when unpopulated. An earlier revision
used marker directives, and a consumer who forgot the import lost their content
with no error; that trade is not worth making.

### An input that does nothing is a bug

Every `input()` must be read by the template or a computed. A dead input is worse
than a missing one: the consumer sets it, sees no error and no effect, and files
it as a component bug. `ui.spec.ts` asserts the ones that are easy to regress.

The same applies in reverse — if a component renders a `<button>`, the screen must
be able to do something with it. `ui-page-header` emits `actionSelected` for
exactly this reason.

### Check both themes

Toggle the theme on `/styleguide` after any styling change. **Anything that does
not change with the theme is a bug in `_semantic.scss`.**

---

## 12. Lint rules that will fail the build

| Rule | Failure | Instead |
|---|---|---|
| `@typescript-eslint/no-explicit-any` | `any` | a real interface, or `unknown` + narrowing |
| `no-empty-lifecycle-method` | empty `ngOnInit` | delete it |
| `component-selector` (features) | non-`app-` prefix | rename the selector |
| `component-selector` (`ui/`) | non-`ui-` prefix, or not kebab-case | rename the selector |
| `@angular-eslint/prefer-standalone` | non-standalone component | add `standalone: true` |
| `template/…` rules | template issues | fix the template, not the rule |
| `consistent-type-definitions` | `type X = {…}` | use `interface X {…}` |

Prettier owns formatting. Run `npm run format` before `npm run lint` so you only
see real problems.

---

## 13. Before you commit

```bash
npm run format
npm run lint
npm run build
npm test
```

All four must pass. The build is the real gate — `strictTemplates` catches type
errors that `lint` will not.