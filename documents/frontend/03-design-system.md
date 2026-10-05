# Frontend — Design System

Bootstrap 5.3 + ng-bootstrap 21, with the legacy theme ported to SCSS.

- **Theme source:** `backend/static/css/theme.css` → `frontend/src/styles/_theme.scss`
- **Icons:** `bootstrap-icons@1.13.1`
- **Charts:** `chart.js@4.5.1` — **no `ng2-charts` wrapper installed**

---

## 1. ⚠ The two-attribute theme contract

The legacy toggle wrote **two** attributes to `<html>`:

```js
document.documentElement.setAttribute('data-theme', theme);
document.documentElement.setAttribute('data-bs-theme', theme);
```

and persisted to `localStorage.theme`.

**Both are required:**

| Attribute | Consumer |
|---|---|
| `data-bs-theme` | Bootstrap 5.3's own dark-mode support, including every ng-bootstrap component |
| `data-theme` | The ported legacy rules in `_theme.scss` |

Setting only one produces a **partially themed UI** — Bootstrap components flip
while custom components do not, or the reverse. This is the single most likely
source of "the dark mode looks broken" reports.

Contract to preserve:

```
localStorage key : "theme"
values           : "light" | "dark"
attributes       : data-theme AND data-bs-theme, both on <html>
```

Implemented in `ThemeService`. Keep this behaviour in any new theming code.

---

## 2. Theme values

`/admin/settings` is the only screen that genuinely uses `base.html` blocks — 40
lines, the smallest template in the corpus — and it is where submission window
settings live.

For the Angular app the theme should be a **user preference**, not an admin-only
setting, unless the requirement is explicitly institution-wide. If it stays
admin-only, make sure the preference is stored server-side rather than only in
`localStorage`; the legacy implementation has no persistence beyond the browser.

---

## 3. SCSS structure

```
frontend/src/
├── styles.scss          entry: imports theme, sets globals
└── styles/
    └── _theme.scss      ported from backend/static/css/theme.css
```

Legacy templates each carried their own inline `<style>` block. Those **must not**
be moved into component `styleUrls` verbatim — see
[02-toolchain.md](02-toolchain.md) §7 for the 4 kB `anyComponentStyle` budget.

Rules of thumb:

- Shared patterns (cards, tables, badges, nav, flash styling) → `src/styles/`.
- Layout only (grid, spacing within one screen) → the component's own styles.
- Bootstrap variables → override in `styles.scss` **before** the Bootstrap import.

---

## 4. Bootstrap setup

```scss
/* styles.scss — order matters */
@import 'bootstrap/scss/functions';
// variable overrides here
@import 'bootstrap/scss/bootstrap';
@import 'styles/theme';
```

### ⚠ Bootstrap JS is not loaded

Only `bootstrap-icons` is imported for assets. Bootstrap's **JavaScript bundle is
deliberately not used** — all interactive behaviour goes through **ng-bootstrap**
components (`NgbDropdown`, `NgbModal`, `NgbNav`, `NgbDatepicker`, …). That is
why `@popperjs/core` is present: ng-bootstrap needs the positioning engine.

Do not add `data-bs-toggle` attributes expecting them to work. They will not.
Use the ng-bootstrap directive on the element instead.

---

## 5. ng-bootstrap 21

Angular 22 standalone integration — import the component, no `NgbModule`.

```ts
@Component({
  selector: 'app-shell',
  imports: [NgbDropdownModule, NgbNavModule],
})
export class Shell {}
```

Common needs for this app:

| Legacy pattern | ng-bootstrap replacement |
|---|---|
| Role switcher dropdown | `NgbDropdown` |
| Review action modals | `NgbModal` |
| Month picker (emits `YYYY-MM`) | `NgbDatepicker` with `ngbDatepicker` |
| Tabbed report sections | `NgbNav` |
| Confirmations before delete | `NgbModal` |

Import the specific component or `NgModule` wrapper per component — not the whole
library into the root.

---

## 6. ⚠ Charts — decision required

`chart.js` is installed; **`ng2-charts` is not**. Chart.js has no Angular
integration of its own.

Only `backend/templates/admin.html` uses charts, driven by
`/admin/analytics_data`, which already returns JSON.

**Recommended: `npm i ng2-charts`.** It wraps Chart.js, registers standalone
components, and handles the destroy lifecycle. The alternative is owning
`new Chart()` in `afterNextRender` plus `chart.destroy()` in `ngOnDestroy` for
every host component.

Either way:

- **Lazy load** the chart route. Chart.js will breach the 500 kB initial budget
  in the eager bundle.
- Register Chart.js components explicitly (`Chart.register(BarController, …)`);
  the tree-shakeable build does not auto-register.
- Apply the `Others`-prefix filter rule from
  [../backend/05-worklog.md](../backend/05-worklog.md) §1, or chart counts will
  not match the legacy dashboard.

---

## 7. Icons

```html
<i class="bi bi-plus-lg"></i>
```

`bootstrap-icons` is copied into the build via `angular.json` assets. Do not add
a second icon set.

---

## 8. Shared UI to extract

From [data/screen-map.json](data/screen-map.json) → `shared_ui_to_extract`:

| Component | Replaces | Notes |
|---|---|---|
| `ShellComponent` | inline navbar + sidebar in **14** templates | Role-conditional links |
| `ThemeToggleComponent` | duplicated toggle scripts | Owns the two-attribute contract |
| `RoleSwitcherComponent` | duplicated dropdown in **6** templates | Calls `POST /api/active-role` |
| `ToastContainer` | flash messages in **22** templates | Backed by a `ToastService` |
| `CategoryTaskFieldComponent` | category select + task textarea, **3** templates | Enforces the `Others` sub-description rule |
| `MonthPickerComponent` | month inputs in **9** templates | Emits `YYYY-MM` strings, never `Date` |

The counts matter: `ShellComponent` alone touches 14 templates and
`ToastContainer` all 22. Extracting these first is what makes the port tractable.

---

## 9. Accessibility

The legacy markup has inconsistent semantics. While porting:

- Real `<button>` elements for actions — not `<div onclick>`.
- `<label for>` on every form control; the legacy forms frequently omit it.
- `aria-current="page"` on the active nav item.
- Modals need focus management and `Escape` handling — ng-bootstrap provides
  this; do not reimplement.
- Contrast: verify the ported theme meets WCAG AA in both light and dark before
  shipping, since the legacy palette was not audited.