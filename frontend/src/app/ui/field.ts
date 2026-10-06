import { afterRenderEffect, Directive, inject, input } from '@angular/core';
import { MatFormField } from '@angular/material/form-field';

/**
 * A labelled form control.
 *
 * This is a directive on `mat-form-field`, not a wrapper component, and that is
 * load-bearing. Angular Material finds a field's control with a content query on
 * `MatFormField`, which only sees directives declared in the *same* template as
 * the field itself. A control projected into a wrapper's `<ng-content>` lives in
 * the consumer's view, so the query never finds it: the field renders empty and
 * Material throws when it dereferences the missing control. Keeping the consumer
 * in charge of `<mat-form-field>` is what lets the control register.
 *
 * The label is Material's own `<mat-label>`, so clicking it focuses the control
 * and screen readers announce it. Never substitute a placeholder for a label —
 * placeholders disappear on focus and on input, which makes long forms unusable.
 *
 * Hints and errors are also Material's, so they follow its own rules: a
 * `<mat-hint>` shows when the field is valid, `<mat-error>` when it is not, and
 * only one is ever visible.
 *
 * `appearance` is deliberately absent: `mat-form-field` already owns it, and two
 * directives on one element declaring the same input is a silent conflict.
 * Styling lives in `src/styles/_material.scss` under `mat-form-field[ui-field]`,
 * because a directive cannot carry styles.
 */
@Directive({
  selector: 'mat-form-field[ui-field]',
  host: {
    '[class.ui-field--full]': 'full()',
    '[class.ui-field--invalid]': 'error() !== undefined',
  },
})
export class UiField {
  private readonly field = inject(MatFormField);

  /** Fill the container width. */
  readonly full = input(true);

  /**
   * Forces the error state on a control that has no validation of its own, such
   * as a static example. A real form should leave this unset and let
   * `MatInput`/`MatSelect` derive the state from its own validators.
   */
  readonly error = input<string>();

  constructor() {
    // Material decides whether to render `<mat-error>` or `<mat-hint>` from
    // `control.errorState` and from nothing else, so a class on the host is not
    // enough: without this the field would paint its outline in the error colour
    // while still showing the hint and no error message. The forced value has to
    // be pushed onto the control.
    //
    // Two assignments are needed and neither alone works:
    //
    // - The matcher, because Material recomputes `errorState` from it on every
    //   value and status change, so a one-off assignment is reverted by the next
    //   keystroke. The default matcher is reinstated when `error` is cleared,
    //   handing the decision back to the control's own validators.
    // - The immediate assignment, because Material recomputes lazily and only
    //   recomputes when something else changes; without it a field that never
    //   receives input keeps showing its hint even though the matcher now agrees.
    //
    // `afterRenderEffect` rather than `effect` because `_control` is assigned by a
    // contentChild query during change detection, which is not a reactive read —
    // a plain effect runs before the query has resolved, finds no control, and
    // never re-runs.
    afterRenderEffect(() => {
      const control = this.field._control as
        | { errorState: boolean; errorStateMatcher?: unknown; stateChanges?: { next(): void } }
        | undefined;
      if (!control) {
        return;
      }

      const forced = this.error() !== undefined;
      control.errorStateMatcher = forced ? { isErrorState: () => true } : undefined;
      control.errorState = forced;

      // This runs after the render that would have picked up the new state, and
      // assigning `errorState` notifies nobody. `MatFormField` re-renders its
      // subscript on `stateChanges`, so without this emission the message area
      // keeps the previous contents until something else happens to trigger a
      // change detection.
      control.stateChanges?.next();
    });
  }
}
