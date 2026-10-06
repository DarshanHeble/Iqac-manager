import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * A button.
 *
 * Wraps Material's MatButton rather than reimplementing it, so we inherit
 * ripples, focus management, form participation, and disabled semantics, and
 * override only appearance. Wrapping beats forking: a hand-rolled `<button>`
 * would have to re-add all of that.
 *
 * Variants map to intent, not to colour:
 *   primary    one dominant action per screen
 *   secondary  the common case; outlined, low weight
 *   ghost      tertiary actions, e.g. a cancel next to a primary
 *   danger     destructive, and always paired with a confirm step
 *
 * Every variant is a flat fill or a hairline. No gradient, no glow, no shadow:
 * on a page of records a button should be findable, not attention-seeking.
 */
@Component({
  selector: 'ui-button',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <button
      matButton
      [class]="'btn--' + variant()"
      [class.btn--block]="block()"
      [disabled]="disabled()"
      [attr.aria-busy]="loading() || null"
      [type]="type()"
    >
      @if (leadingIcon(); as name) {
        <mat-icon [class.btn__spinner]="loading()" aria-hidden="true">{{ name }}</mat-icon>
      }

      <span class="btn__label"><ng-content /></span>

      @if (trailingGlyph(); as name) {
        <mat-icon aria-hidden="true">{{ name }}</mat-icon>
      }
    </button>
  `,
  styles: `
    .btn--primary {
      --_bg: var(--ui-primary);
      --_fg: var(--ui-on-primary);
      --_border: var(--ui-primary);
      --_hover-bg: var(--ui-primary-hover);
      --_hover-fg: var(--ui-on-primary);
    }

    .btn--secondary {
      --_bg: var(--ui-surface-raised);
      --_fg: var(--ui-text);
      --_border: var(--ui-border-strong);
      --_hover-bg: var(--ui-surface-muted);
      --_hover-fg: var(--ui-text);
    }

    .btn--ghost {
      --_bg: transparent;
      --_fg: var(--ui-text-muted);
      --_border: transparent;
      --_hover-bg: var(--ui-surface-muted);
      --_hover-fg: var(--ui-text);
    }

    .btn--danger {
      --_bg: var(--ui-danger);
      --_fg: var(--ui-on-danger);
      --_border: var(--ui-danger);
      --_hover-bg: var(--ui-danger-container);
      --_hover-fg: var(--ui-on-danger-container);
    }

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: var(--ui-space-2);
      min-block-size: var(--ui-control-height);
      padding-inline: var(--ui-control-padding-inline);
      border-radius: var(--ui-radius-sm);
      font: var(--ui-text-label-weight) var(--ui-text-label-size) / var(--ui-text-label-line)
        var(--ui-text-label-family);
      letter-spacing: var(--ui-text-label-tracking);
      background: var(--_bg);
      color: var(--_fg);
      /* A hairline rather than Material's stock outlined treatment, and no
         elevation — a button sits on the page, it does not float above it. */
      box-shadow: inset 0 0 0 var(--ui-rule-width) var(--_border);
      border: none;
      transition:
        background-color var(--ui-duration-fast) var(--ui-ease-standard),
        color var(--ui-duration-fast) var(--ui-ease-standard),
        box-shadow var(--ui-duration-fast) var(--ui-ease-standard);

      &:hover:not(:disabled) {
        background: var(--_hover-bg);
        color: var(--_hover-fg);
      }

      &:active:not(:disabled) {
        /* Pressing reads as the surface being pushed in, not a colour swap. */
        box-shadow: inset 0 0 0 var(--ui-rule-width) var(--_border);
        transform: translateY(1px);
      }

      &:disabled {
        opacity: 0.55;
      }

      /* Material puts its own ripple layer; keep it subtle so it does not read
         as a saturated brand wash over the navy fill. */
      ::ng-deep .mat-mdc-button-persistent-ripple::before {
        background-color: currentColor;
      }
    }

    .btn--block {
      inline-size: 100%;
    }

    .btn__label {
      /* Keeps the button at its control height even with no projected text. */
      white-space: nowrap;
    }

    .btn__spinner {
      animation: ui-button-spin var(--ui-duration-slow) linear infinite;
    }

    @keyframes ui-button-spin {
      to {
        transform: rotate(360deg);
      }
    }

    /* Respect a reduced-motion preference for the loading spinner too. */
    @media (prefers-reduced-motion: reduce) {
      .btn__spinner {
        animation: none;
      }
    }
  `,
})
export class UiButton {
  /** Visual intent. Never pass a colour. */
  readonly variant = input<'primary' | 'secondary' | 'ghost' | 'danger'>('secondary');

  /** Icon. Hidden from assistive tech; the label carries the meaning. */
  readonly icon = input<string>();

  /** Where `icon` sits relative to the label. */
  readonly iconPosition = input<'leading' | 'trailing'>('leading');

  /** Trailing icon, e.g. an open-in-new arrow. */
  readonly trailingIcon = input<string>();

  /** Fill the available inline size. */
  readonly block = input(false);

  readonly disabled = input(false);

  /** Shows a spinner and marks the button busy. */
  readonly loading = input(false);

  /** Native button type. Defaults to "button" so it never submits by accident. */
  readonly type = input<'button' | 'submit' | 'reset'>('button');

  /**
   * The glyph rendered before the label.
   *
   * Loading replaces any icon rather than sitting beside it: a button whose
   * contents change when it is pressed keeps its width and does not reflow the
   * row it sits in.
   */
  protected readonly leadingIcon = computed(() => {
    if (this.loading()) return 'progress_activity';
    return this.iconPosition() === 'leading' ? this.icon() : undefined;
  });

  /** The glyph rendered after the label: `trailingIcon`, or `icon` when asked. */
  protected readonly trailingGlyph = computed(() => {
    if (this.loading()) return undefined;
    return this.iconPosition() === 'trailing'
      ? (this.icon() ?? this.trailingIcon())
      : this.trailingIcon();
  });
}
