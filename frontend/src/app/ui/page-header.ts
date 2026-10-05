import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { UiBadge } from './badge';

export interface PageHeaderAction {
  readonly label: string;
  readonly icon?: string;
  readonly variant?: 'primary' | 'secondary' | 'ghost';
}

/**
 * The heading block at the top of every screen.
 *
 * Carries three things and nothing else: what screen this is, what it is for
 * (the description), and what you can do here (the actions). Keeping actions in
 * the header is what stops every migrated screen from growing its own toolbar
 * with a different arrangement.
 *
 * `overline` is for the section a screen belongs to ("Faculty Records"), not a
 * subtitle — it is the one tracked-out step in the type system, so it has to
 * earn its place.
 */
@Component({
  selector: 'ui-page-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, UiBadge],
  template: `
    <header class="page-header">
      <div class="page-header__main">
        @if (overline()) {
          <p class="overline page-header__overline">{{ overline() }}</p>
        }

        <div class="page-header__title-row">
          <h1 class="page-header__title">{{ title() }}</h1>
          @if (badge(); as label) {
            <ui-badge [tone]="tone() ?? 'neutral'">{{ label }}</ui-badge>
          }
        </div>

        @if (description()) {
          <p class="lead page-header__description">{{ description() }}</p>
        }
      </div>

      @if (actions().length) {
        <div class="page-header__actions">
          @for (action of actions(); track action.label) {
            <button
              matButton
              class="page-header__action"
              [attr.data-variant]="action.variant ?? 'secondary'"
            >
              @if (action.icon) {
                <mat-icon aria-hidden="true">{{ action.icon }}</mat-icon>
              }
              {{ action.label }}
            </button>
          }
        </div>
      }
    </header>
  `,
  styles: `
    @use 'typography' as type;

    .page-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: var(--ui-space-5);
      flex-wrap: wrap;
      padding-block-end: var(--ui-space-5);
      /* The hairline separates the header from the content below, in place of a
         heavy divider or extra vertical space. */
      border-block-end: var(--ui-rule-width) solid var(--ui-border);
      margin-block-end: var(--ui-space-6);
    }

    .page-header__main {
      min-inline-size: 0;
      flex: 1;
    }

    .page-header__overline {
      margin-block-end: var(--ui-space-2);
    }

    .page-header__title-row {
      display: flex;
      align-items: center;
      gap: var(--ui-space-3);
      flex-wrap: wrap;
    }

    .page-header__title {
      @include type.heading(h1);
      min-inline-size: 0;
    }

    .page-header__description {
      margin-block-start: var(--ui-space-2);
    }

    .page-header__actions {
      display: flex;
      align-items: center;
      gap: var(--ui-space-2);
      flex-shrink: 0;
    }

    /*
     * Header actions are secondary by default: the screen is the destination, not
     * a form with a submit. A header should not carry the loudest button on the
     * page, so these stay outlined regardless of the action's variant — the
     * variant only decides emphasis among them.
     */
    .page-header__action {
      min-block-size: var(--ui-control-height);
      padding-inline: var(--ui-control-padding-inline);
      border-radius: var(--ui-radius-sm);
      font: var(--ui-text-label-weight) var(--ui-text-label-size) / var(--ui-text-label-line)
        var(--ui-text-label-family);
      color: var(--ui-text);
      box-shadow: inset 0 0 0 1px var(--ui-border-strong);
    }

    .page-header__action[data-variant='primary'] {
      background: var(--ui-primary);
      color: var(--ui-on-primary);
      box-shadow: inset 0 0 0 1px var(--ui-primary);
    }

    .page-header__action[data-variant='ghost'] {
      box-shadow: none;
      color: var(--ui-text-muted);
    }

    .page-header__action:hover {
      background: var(--ui-surface-muted);
    }

    .page-header__action[data-variant='primary']:hover {
      background: var(--ui-primary-hover);
      color: var(--ui-on-primary);
    }

    @media (width <= 640px) {
      .page-header {
        align-items: stretch;
        flex-direction: column;
      }

      .page-header__actions {
        justify-content: flex-start;
      }
    }
  `,
})
export class UiPageHeader {
  /** Section label above the title, e.g. "Faculty Records". */
  readonly overline = input<string>();

  /** Screen title. Rendered as the h1 — exactly one per screen. */
  readonly title = input.required<string>();

  /** One line explaining what this screen is for. */
  readonly description = input<string>();

  /** Optional status chip beside the title. */
  readonly badge = input<string>();

  /** Badge tone. Ignored when `badge` is unset. */
  readonly tone = input<'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'>();

  /** Header actions. Rendered right, wrapping on narrow screens. */
  readonly actions = input<readonly PageHeaderAction[]>([]);
}
