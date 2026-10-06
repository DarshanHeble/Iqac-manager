import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { UiBadge } from './badge';

/**
 * A titled block of content within a screen.
 *
 * Distinct from `ui-card` in purpose: a card is a bounded container, a section
 * is a grouping of content on the page. Sections are not boxed — they use an
 * overline label and vertical space, which keeps a long screen from turning into
 * a stack of identical panels.
 */
@Component({
  selector: 'ui-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, UiBadge],
  template: `
    <section class="section" [attr.aria-labelledby]="headingId">
      <header class="section__header">
        <div class="section__heading-group">
          @if (label()) {
            <p class="overline section__label">{{ label() }}</p>
          }
          <h2 class="section__title" [id]="headingId">{{ title() }}</h2>
          @if (description()) {
            <p class="section__description">{{ description() }}</p>
          }
        </div>

        @if (badge(); as value) {
          <ui-badge [tone]="tone() ?? 'neutral'">{{ value }}</ui-badge>
        }

        <div class="section__actions">
          <ng-content select="[ui-section-actions]" />
        </div>
      </header>

      <div class="section__body">
        <ng-content />
      </div>
    </section>
  `,
  styles: `
    @use 'typography' as type;

    .section + .section {
      margin-block-start: var(--ui-space-10);
    }

    .section__header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: var(--ui-space-4);
      flex-wrap: wrap;
      margin-block-end: var(--ui-space-4);
    }

    .section__heading-group {
      min-inline-size: 0;
      flex: 1;
    }

    .section__label {
      margin-block-end: var(--ui-space-1);
    }

    .section__title {
      @include type.heading(h3);
    }

    .section__description {
      @include type.text-role(body-sm);
      color: var(--ui-text-muted);
      margin-block-start: var(--ui-space-2);
      max-inline-size: var(--ui-measure);
    }

    .section__actions {
      display: flex;
      align-items: center;
      gap: var(--ui-space-2);
      flex-shrink: 0;
    }

    .section__actions:empty {
      display: none;
    }
  `,
})
export class UiSection {
  /** Context label above the title. Use only when the grouping is ambiguous. */
  readonly label = input<string>();

  /** Section title. Rendered as the h2. */
  readonly title = input.required<string>();

  /** Supporting line under the title. */
  readonly description = input<string>();

  /** Optional status chip. */
  readonly badge = input<string>();

  /** Badge tone. Ignored when `badge` is unset. */
  readonly tone = input<'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'>();

  /** Stable id so `aria-labelledby` points at the real heading. */
  protected readonly headingId = `ui-section-${crypto.randomUUID().slice(0, 8)}`;
}
