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
     ↓ p.scale('brand', 700), p.layout('rail-width')
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
| `p.layout('rail-width')` | layout dimension |
| `p.space(4)`, `p.radius('sm')`, `p.icon('sm')` | scale steps |
| `p.shadow(3)`, `p.shape('lg')` | elevation, Material corners |

Two other constraints worth knowing before editing these files:

- **No dotted map access.** `$t.family` is a parse error in the pinned Sass
  (1.104.1). Use `map.get($t, family)`.
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
| `ui-field` | wraps `mat-form-field`; label, hint, and error are separate inputs |
| `ui-page-header` | overline + h1 + description + actions, the top of every screen |
| `ui-section` | titled content grouping; not boxed |
| `ui-stat` | one figure, tabular numerals, optional trend |
| `ui-empty-state` | what is missing, why, and what to do |
| `ui-record-row` | entity + status, with the signature 3px leading rule |
| `ui-card-footer` etc. | projection-slot markers (see below) |

### Wrapping Material, not forking it

`ui-button` and `ui-field` wrap Material and override appearance only. That keeps
ripples, focus management, form participation, and disabled semantics. A
hand-rolled `<button>` would have to re-add all of it.

### Projection slots

Angular has no built-in "was anything projected here" check, so each optional slot
is a zero-template attribute component queried with `contentChild()`:

```html
<ui-card heading="Summary">
  <button ui-card-actions>View report</button>
</ui-card>
```

If nothing matches, the slot is not rendered at all. The `recordTitle`,
`recordMeta`, and `recordDetail` slots are plain attributes — they are always
present together, so they need no detection.

---

## 5. The styleguide is the test

`/styleguide` renders every token and component in the live theme. It exists
because a token table in a document proves nothing: seeing the same page in light
and dark, at real sizes, is the only way to catch a token that was never wired up
or a contrast pair that fails in one theme.

Switch the theme and everything must change together. **Anything that stays put is
a bug in `_semantic.scss`.**

`src/app/ui/ui.spec.ts` additionally asserts mechanically that no component style
contains a raw hex or a literal `font-size`.

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
- `ui-field` renders a real `<label>` via Material. Never substitute a placeholder.
- A skip link as the first tab stop, targeting `#main-content`.
- One `:focus-visible` treatment app-wide — a ring, never `outline: none` alone.
- `prefers-reduced-motion` disables transitions, smooth scroll, and the button
  spinner.
- `.visually-hidden` for content that is read but not shown.

Still to verify before shipping a screen: WCAG AA contrast in both themes. The
palette was carried over from the legacy stylesheet, which was never audited.