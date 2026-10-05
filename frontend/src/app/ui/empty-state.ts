import { ChangeDetectionStrategy, Component, contentChild, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * Marker for the primary call to action in `<ui-empty-state>`.
 *
 * Angular has no built-in "was anything projected here" check, so the state
 * component queries for this marker instead of rendering its action slot
 * unconditionally. That keeps the spacing gap in the flex column from being
 * applied to an empty box when a screen provides no action.
 */
@Component({
  selector: '[ui-empty-action]',
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UiEmptyStateAction {}

/** Secondary/supporting slot, e.g. "Contact the academic office". */
@Component({
  selector: '[ui-empty-secondary]',
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UiEmptyStateSecondary {}

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

      @if (actionSlot()) {
        <div class="empty__action">
          <ng-content select="[ui-empty-action]" />
        </div>
      }

      @if (secondarySlot()) {
        <p class="empty__secondary">
          <ng-content select="[ui-empty-secondary]" />
        </p>
      }
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
  `,
})
export class UiEmptyState {
  /** What is missing, stated plainly. */
  readonly title = input.required<string>();

  /** Why it might be missing, or what to do. */
  readonly description = input<string>();

  /** Material Symbols name. Keep it neutral; tone is not the message. */
  readonly icon = input<string>('inbox');

  protected readonly actionSlot = contentChild(UiEmptyStateAction);
  protected readonly secondarySlot = contentChild(UiEmptyStateSecondary);
}
