# Frontend — Design System

Angular Material 22 (M3 token system) on top of a single-source SCSS token layer.
Nothing is styled with a literal value; everything resolves through a token.

- **Tokens:** `frontend/src/styles/_palette.scss` → `_semantic.scss` → `_tokens.scss`
- **Material:** `@angular/material@22.2.1` + `@angular/cdk@22.2.1`, fed by `_material.scss`
- **Components:** `frontend/src/app/ui/` — standalone, no `NgModule`
- **Reference:** `/styleguide` renders every token and component in the live theme
- **Icons:** Material Symbols Rounded, loaded in `index.html`

---

## 1. The token pipeline

Four files, one direction. This is the core of the design system: change a value
at the top and it reaches both our components and every Angular Material
component.

```
_palette.scss      raw ramps + scales        #003366 lives here, and nowhere else
_breakpoints.scss  responsive thresholds    bp.below(sm), bp.atleast(lg)
     ↓ p.scale('brand', 700), p.single('white'), p.layout('rail-width')
_semantic.scss     role per theme            primary, surface-container-low, outline-variant…
     ↓
_tokens.scss       → --ui-* custom properties
_material.scss     → --mat-sys-* tokens       mat.theme-overrides(semantic.$light)

_reset.scss        element normalisation
_elements.scss     the global CSS system     what h1–h6, p, caption, figcaption mean
_layout.scss       app shell + flow          .rail, .topbar, .content, .flow, .cluster
_utilities.scss    single-purpose helpers    .mt-4, .text-muted, .spine
```

`_material.scss` receives **the same `semantic.$light` / `semantic.$dark` maps**
that `_tokens.scss` uses. A Material select cannot end up navy while our button
ends up somewhere else, because there is only one place either colour is decided.

### Accessing maps from Sass

Map keys contain dashes, so `p.$layout.rail-width` is a parse error (Sass reads it
as subtraction). Use the accessors in `_palette.scss`:

| Call | Returns |
|---|---|
| `p.scale('brand', 700)` | raw ramp value |
| `p.status('success', 'base')` | status value |
| `p.single('white')` | one-off colour not on a ramp |
| `p.layout('rail-width')` | layout dimension |
| `p.breakpoint(sm)` | responsive threshold |
| `p.space(4)`, `p.radius('sm')`, `p.icon('sm')` | scale steps |
| `p.shadow(3)`, `p.shape('lg')` | elevation, Material corners |

Every accessor errors on an unknown key rather than returning `null`, so a typo
fails the build instead of emitting `var(--ui-primary: )`.

### `_semantic.scss` names no colour

Each theme maps a role to a palette value and nothing else — not one hex, not one
`rgb()`. Values that are genuinely one-off (white, the teal tertiary family, the
six `surface-container` tints, the alpha inks) live in `$singles` in
`_palette.scss` and are reached with `p.single()`.

That is what lets a test assert *"no style layer except `_palette.scss` contains a
hex"*. Without it, "single source of truth" is a claim rather than a fact.

Two other constraints worth knowing before editing these files:

- **No dotted map access.** `$t.family` is a parse error in the pinned Sass
  (1.104.1). Use `map.get($t, family)`.
- **Quote CSS colour keywords as map keys.** `white: #fff` is parsed as the
  *colour* `#fff`, not the string `'white'`, so `p.single('white')` then fails.
  It must be `'white': #fff`. Verified on 1.104.1.
- **No `if()`.** Deprecated in favour of `@if` / `@else`. Values are assigned to a
  variable first, then interpolated.

---

## 2. ⚠ The theme contract

The legacy toggle wrote **two** attributes, but only one was ever consumed:

| Attribute | Written by legacy? | Consumed by |
|---|---|---|
| `data-theme` | yes | the legacy rules in `theme.css` |
| `data-bs-theme` | yes | **nothing** — no template or stylesheet reads it |

Earlier revisions of this document claimed `data-bs-theme` was required for
Bootstrap's native dark mode. That is wrong for this codebase: the templates load
Bootstrap for layout and components but never theme it, so setting
`data-bs-theme` had no effect. Verified against all 22 templates.

The Angular app keeps writing both, for compatibility rather than necessity:

```
localStorage key : "theme"
values           : "light" | "dark"
attributes       : data-theme  (authoritative — scopes every --ui-* and --mat-sys-*)
                   data-bs-theme (written, not depended on)
```

`data-theme` is the authority: `_tokens.scss` scopes every colour token to
`[data-theme='light']` / `[data-theme='dark']`, and `_material.scss` scopes the
Material theme the same way. One attribute change re-themes the whole app.

`index.html` applies the stored theme in an inline script before first paint, so a
dark-mode user never sees a white flash. `ThemeService` keeps the DOM in sync
afterwards. If you replace that inline script, you have to replace it with
something that still runs before paint.

---

## 3. Typography

Two families, and where the family changes is the single biggest lever
separating this from a templated look:

| Role | Family | Size |
|---|---|---|
| `display-lg` … `h3` | Source Serif 4 | 2.75rem → 1.375rem |
| `h4` … `h6`, all body, UI | Inter | 1.125rem → 0.8125rem |
| `code` | JetBrains Mono | 0.875rem |

The serif/sans crossing sits between `h3` and `h4`: that is where a heading stops
being a title and starts labelling content.

Both webfonts have a full system-stack fallback, so the app renders correctly with
no network access to Google Fonts.

**Roles, not sizes.** A component never writes `font-size`; it selects a role:

```scss
@include type.heading(h4);      // in a component stylesheet
// or, from the global classes in _elements.scss:
<h3>…</h3>  <p class="caption">…</p>  <span class="label">…</span>
```

`figcaption` is deliberately separate from `caption` — it is legal/technical
metadata under a figure, so it is always muted and always tight.

Component stylesheets can `@use 'typography' as type;` because `angular.json`
sets `stylePreprocessorOptions.includePaths` to `src/styles`.

---

## 4. Components

`frontend/src/app/ui/`, all standalone, all `OnPush`, all exported from
`ui/index.ts`.

| Component | Purpose |
|---|---|
| `ui-badge` | status pill; the one fully-round element, because a pill reads as a marker not a container |
| `ui-button` | wraps `matButton`; variants are intent (`primary`/`secondary`/`ghost`/`danger`), never colour |
| `ui-card` | flat panel — hairline border, no shadow by default |
| `ui-field` | directive on `mat-form-field`; aligns type and outline to the app's tokens |
| `ui-page-header` | overline + h1 + description + actions, the top of every screen; emits `actionSelected` |
| `ui-section` | titled content grouping; not boxed |
| `ui-stat` | one figure, tabular numerals, optional trend |
| `ui-empty-state` | what is missing, why, and what to do |
| `ui-record-row` | entity + status, with the signature 3px leading rule |

### A component that renders a control must make it work

`ui-page-header` renders its own buttons from structured input, because the header
owns the arrangement and the emphasis. That makes it responsible for making them
work: each `PageHeaderAction` carries an `id`, and pressing one emits
`actionSelected`. A header action that does nothing is worse than no header
actions at all — it looks like a working control and is not one.

```html
<ui-page-header
  title="Submission register"
  [actions]="[{ id: 'add', label: 'Add entry', variant: 'primary' }]"
  (actionSelected)="onAction($event)"
/>
```

### Wrapping Material, not forking it

`ui-button` and `ui-field` wrap Material and override appearance only. That keeps
ripples, focus management, form participation, and disabled semantics. A
hand-rolled `<button>` would have to re-add all of it.

`ui-field` is a directive rather than a wrapper component, and that is forced
rather than stylistic. Material resolves a field's control with a content query on
`MatFormField`, which only sees directives declared in the same template as the
field itself. Project `<input matInput>` through a wrapper's `<ng-content>` and
the query returns nothing: the field renders blank and Material throws reading
`controlType` off the missing control, at runtime, with no build-time error. So
the consumer owns the element:

```html
<mat-form-field ui-field>
  <mat-label>Academic year</mat-label>
  <mat-hint>Format: 2025–26</mat-hint>
  <input matInput />
</mat-form-field>
```

Two consequences worth knowing. `appearance` is not an input on `ui-field` —
`mat-form-field` already owns that name, and two directives on one element
declaring the same input is a silent conflict; pass it to the field. And since
Angular 22 directives cannot carry `styles`, the rules live in `_material.scss`
under `mat-form-field[ui-field]`, scoped by the marker attribute so they reach
Material's internals without `::ng-deep` and without leaking into unmarked fields.

### Projection slots

An optional slot is a plain attribute used as a projection hook — **not a
directive**:

```html
<ui-card heading="Summary">
  <button ui-card-actions>View report</button>
  <span ui-card-footer>Updated 12 March</span>
</ui-card>
```

Nothing is imported for these. An earlier revision defined them as zero-template
marker components queried with `contentChild()`, which meant a consumer had to
import a marker class per slot — and if they forgot one, the projected content
was silently discarded with no error. A design system whose usage error is
invisible content loss is a trap, so the markers are gone.

The wrapper is always in the DOM and collapses when unpopulated, via `:empty` on
the leaf slots and `:not(:has(…))` on `ui-card`'s header (its own `@if` blocks
leave comment nodes, so `:empty` cannot match there).

Slots: `ui-card` takes `ui-card-actions` and `ui-card-footer`; `ui-empty-state`
takes `ui-empty-action` and `ui-empty-secondary`; `ui-section` takes
`ui-section-actions`; `ui-record-row` takes `ui-record-title`, `ui-record-meta`,
`ui-record-detail`, and `ui-record-trailing`.

---

## 5. The styleguide is the test

`/styleguide` renders every token and component in the live theme. It exists
because a token table in a document proves nothing: seeing the same page in light
and dark, at real sizes, is the only way to catch a token that was never wired up
or a contrast pair that fails in one theme.

Switch the theme and everything must change together. **Anything that stays put is
a bug in `_semantic.scss`.**

### What the tests actually enforce

`src/app/ui/ui.spec.ts` fails the run on:

| Rule | Why it matters |
|---|---|
| no hex in any component style | a hardcoded colour stops responding to the theme |
| no hex in any `src/styles/` layer **except** `_palette.scss` | makes the palette a real single source of truth rather than a claim |
| no literal `font-size` | forces a role from `_typography.scss` |
| no literal `padding`/`margin`/`gap`/`inset` | forces a `--ui-space-*` step |
| no raw `@media (width …)` | a forked threshold nobody can find; use `bp.below()`/`bp.atleast()` |
| slots collapse when unpopulated | guards the projection behaviour above |
| every input does something | a dead input is worse than a missing one: the consumer sets it, sees no error, and it is ignored |

Breakpoint values live in `_palette.scss` and are emitted by `_breakpoints.scss`;
media queries cannot read a custom property, so they must be a build-time value.
That is exactly why they are written once and mixed in.

---

## 6. Charts — decision still required

`chart.js` is installed; **no Angular wrapper is.** Chart.js has no integration of
its own, and only `backend/templates/admin.html` uses charts (via
`/admin/analytics_data`).

Either install `ng2-charts`, or own `new Chart()` in `afterNextRender` plus
`chart.destroy()` in `ngOnDestroy` per host component.

- **Lazy load the chart route.** Chart.js breaches the 500 kB initial budget.
- Register controllers explicitly (`Chart.register(BarController, …)`); the
  tree-shakeable build does not auto-register.
- Apply the `Others`-prefix filter rule from
  [../backend/05-worklog.md](../backend/05-worklog.md) §1, or chart counts will
  not match the legacy dashboard.

---

## 7. Icons

```html
<mat-icon aria-hidden="true">download</mat-icon>
```

Material Symbols Rounded, linked in `index.html`. Always `aria-hidden` when
adjacent to a text label — the glyph is decoration, the label is the meaning.
Icon sizes come from `--ui-icon-*` (a `$icon` scale in `_palette.scss`), because a
Material icon is a font glyph and its size is a `font-size`.

Do not add a second icon set.

---

## 8. Legacy aliases

`_tokens.scss` still emits `--bg-color`, `--card-bg`, `--border-color`,
`--primary-color`, `--text-color`, `--sidebar-width`, `--navbar-height` as aliases
onto the `--ui-*` values. This keeps any screen still served by Flask agreeing
exactly with an Angular screen. Delete the aliases once migration completes.

---

## 9. Accessibility

Enforced in the components, not left to each screen:

- One `h1` per screen (`ui-page-header`); the shell uses `h2` so routed screens own
  the `h1`.
- `ui-section` sets `aria-labelledby` to its real heading.
- `ui-field` renders a real `<label>` via Material's `<mat-label>`, tied to the
  control's generated id. Never substitute a placeholder.
- A skip link as the first tab stop, targeting `#main-content`.
- One `:focus-visible` treatment app-wide — a ring, never `outline: none` alone.
- `prefers-reduced-motion` disables transitions, smooth scroll, and the button
  spinner.
- `.visually-hidden` for content that is read but not shown.

Still to verify before shipping a screen: WCAG AA contrast in both themes. The
palette was carried over from the legacy stylesheet, which was never audited.