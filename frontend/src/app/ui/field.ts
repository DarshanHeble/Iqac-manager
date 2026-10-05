import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatFormFieldModule } from '@angular/material/form-field';

/**
 * A labelled form control.
 *
 * Wraps Material's field appearance so validation styling, floating label, and
 * hint text all come from Angular Material, then aligns the typography with the
 * rest of the app.
 *
 * The label is always rendered as a real `<label>` via Material's own markup, so
 * clicking it focuses the control and screen readers announce it. Never
 * substitute a placeholder for a label — placeholders disappear on focus and
 * on input, which makes long forms unusable.
 *
 * `hint` and `error` are separate from the label so the required/optional
 * marker never competes with guidance text.
 */
@Component({
  selector: 'ui-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatFormFieldModule],
  template: `
    <mat-form-field
      [appearance]="appearance()"
      [class.ui-field--invalid]="invalid()"
      [class.ui-field--full]="full()"
    >
      @if (label()) {
        <mat-label>{{ label() }}</mat-label>
      }

      <ng-content />

      @if (hint() && !invalid()) {
        <mat-hint>{{ hint() }}</mat-hint>
      }

      @if (error(); as message) {
        <mat-error>{{ message }}</mat-error>
      }
    </mat-form-field>
  `,
  styles: `
    @use 'typography' as type;

    :host {
      display: block;
    }

    :host(.ui-field--full) {
      inline-size: 100%;
    }

    mat-form-field {
      inline-size: 100%;
    }

    /*
     * Material's default label is tracked-out uppercase. That is a reasonable
     * default and wrong here: this app's labels are sentence case and sit at
     * label scale, matching the .label role used elsewhere.
     */
    ::ng-deep .mat-mdc-form-field-label {
      @include type.text-role(label);
      letter-spacing: var(--ui-text-label-tracking);
      text-transform: none;
      color: var(--ui-text-muted);
    }

    ::ng-deep .mat-mdc-form-field .mdc-floating-label--float-above {
      color: var(--ui-text-muted);
    }

    /* Focused field: the label takes the primary role so the active control is
       unambiguous when several fields sit in one row. */
    ::ng-deep .mat-mdc-form-field.mat-focused .mat-mdc-floating-label {
      color: var(--ui-primary);
    }

    ::ng-deep .mat-mdc-form-field .mdc-text-field__input {
      @include type.text-role(body);
      color: var(--ui-text);
    }

    ::ng-deep .mat-mdc-form-field .mat-mdc-form-field-hint {
      @include type.text-role(caption);
      color: var(--ui-text-muted);
    }

    ::ng-deep .mat-mdc-form-field .mat-mdc-form-field-error {
      @include type.text-role(caption);
      color: var(--ui-danger);
    }

    /*
     * Restrained outline, not Material's heavier double border. The field sits on
     * a page of hairlines, so it should match them.
     */
    ::ng-deep .mat-mdc-text-field-wrapper {
      border-radius: var(--ui-radius-sm);
    }

    ::ng-deep .mat-mdc-form-field.mat-form-field-appearance-outline .mdc-notched-outline__leading,
    ::ng-deep .mat-mdc-form-field.mat-form-field-appearance-outline .mdc-notched-outline__notch,
    ::ng-deep .mat-mdc-form-field.mat-form-field-appearance-outline .mdc-notched-outline__trailing {
      border-color: var(--ui-border-strong);
    }

    ::ng-deep .mat-mdc-form-field.mat-focused .mdc-notched-outline__leading,
    ::ng-deep .mat-mdc-form-field.mat-focused .mdc-notched-outline__notch,
    ::ng-deep .mat-mdc-form-field.mat-focused .mdc-notched-outline__trailing {
      border-color: var(--ui-primary);
      border-width: var(--ui-focus-width);
    }

    ::ng-deep .ui-field--invalid .mdc-notched-outline__leading,
    ::ng-deep .ui-field--invalid .mdc-notched-outline__notch,
    ::ng-deep .ui-field--invalid .mdc-notched-outline__trailing {
      border-color: var(--ui-danger);
    }
  `,
})
export class UiField {
  /** Field label. Required in practice — do not ship a field without one. */
  readonly label = input<string>();

  /** Guidance text below the control. Suppressed while an error is showing. */
  readonly hint = input<string>();

  /** Error message. Its presence is what puts the field in the error state. */
  readonly error = input<string>();

  /** Material field appearance. Outline suits dense, record-style forms. */
  readonly appearance = input<'outline' | 'fill'>('outline');

  /** Fill the container width. */
  readonly full = input(true);

  /** Error state follows the presence of an error message. */
  protected readonly invalid = computed(() => this.error() !== undefined);
}
