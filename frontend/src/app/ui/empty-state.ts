import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * The "nothing here yet" state.
 *
 * Empty states are the screen people judge a product by, so this is a real
 * component rather than an ad-hoc template in each feature: it always says what
 * is missing, why it might be missing, and what to do about it, and it offers
 * the action as content instead of leaving the user to navigate away and find it.
 *
 * Not boxed. An empty state is a message, and boxing it would put a panel inside
 * a panel.
 *
 * The `ui-empty-action` and `ui-empty-secondary` slots are plain projection
 * hooks, not directives. An unpopulated slot collapses via `:empty`, which keeps
 * the flex `gap` from spacing an empty box and needs no import from the consumer.
 */
@Component({
  selector: 'ui-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div class="empty" role="status">
      @if (icon(); as name) {
        <mat-icon class="empty__icon" aria-hidden="true">{{ name }}</mat-icon>
      }

      <h3 class="empty__title">{{ title() }}</h3>

      @if (description()) {
        <p class="empty__description">{{ description() }}</p>
      }

      <div class="empty__action">
        <ng-content select="[ui-empty-action]" />
      </div>

      <p class="empty__secondary">
        <ng-content select="[ui-empty-secondary]" />
      </p>
    </div>
  `,
  styles: `
    @use 'typography' as type;

    .empty {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: var(--ui-space-3);
      padding: var(--ui-space-12) var(--ui-space-6);
      max-inline-size: 44ch;
      margin-inline: auto;
    }

    .empty__icon {
      font-size: var(--ui-icon-xl);
      inline-size: var(--ui-icon-xl);
      block-size: var(--ui-icon-xl);
      color: var(--ui-border-strong);
      /* Material icons sit optically high; nudge down to match the cap height
         of the title below. */
      margin-block-end: var(--ui-space-1);
    }

    .empty__title {
      @include type.heading(h4);
    }

    .empty__description {
      @include type.text-role(body);
      color: var(--ui-text-muted);
    }

    .empty__action {
      margin-block-start: var(--ui-space-2);
    }

    .empty__secondary {
      @include type.text-role(caption);
      color: var(--ui-text-muted);
      margin-block-start: var(--ui-space-2);
    }

    /* Collapsed rather than guarded in the template: see the class docblock. */
    .empty__action:empty,
    .empty__secondary:empty {
      display: none;
    }
  `,
})
export class UiEmptyState {
  /** What is missing, stated plainly. */
  readonly title = input.required<string>();

  /** Why it might be missing, or what to do. */
  readonly description = input<string>();

  /** Material Symbols name. Keep it neutral; tone is not the message. */
  readonly icon = input<string>('inbox');
}
