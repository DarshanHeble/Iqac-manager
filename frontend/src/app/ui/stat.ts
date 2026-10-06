import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * One figure on a summary strip.
 *
 * Built around the number: the value is the largest thing in the component, set
 * at the numeral role with tabular figures so a column of stats aligns and does
 * not shift as values refresh. The label is quiet and sits above it, because you
 * read a stat by recognising the label first.
 *
 * `trend` is optional and additive. It is a signed change with an explicit
 * `trendLabel`, never a bare arrow — "12%" alone does not say compared to what.
 */
@Component({
  selector: 'ui-stat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div class="stat" [attr.data-tone]="tone()">
      <p class="stat__label">
        {{ label() }}
        @if (hint()) {
          <span class="stat__hint" [attr.title]="hint()">
            <mat-icon aria-hidden="true">info</mat-icon>
            <span class="visually-hidden">{{ hint() }}</span>
          </span>
        }
      </p>

      <p class="stat__value num">{{ value() }}</p>

      @if (trend(); as change) {
        <p class="stat__trend" [attr.data-direction]="trendDirection()">
          <mat-icon aria-hidden="true">{{ trendIcon() }}</mat-icon>
          <span class="stat__trend-value">{{ change }}</span>
          @if (trendLabel()) {
            <span class="stat__trend-label">{{ trendLabel() }}</span>
          }
        </p>
      }
    </div>
  `,
  styles: `
    @use 'breakpoints' as bp;
    @use 'typography' as type;

    .stat {
      min-inline-size: 0;
      padding-inline-end: var(--ui-space-5);
      /* A vertical rule between stats instead of separate boxes: this is a
         summary strip, not a set of cards. */
      border-inline-end: var(--ui-rule-width) solid var(--ui-border);
    }

    .stat:last-child {
      border-inline-end: none;
      padding-inline-end: 0;
    }

    .stat__label {
      display: flex;
      align-items: center;
      gap: var(--ui-space-1);
      font: var(--ui-text-label-weight) var(--ui-text-label-size) / var(--ui-text-label-line)
        var(--ui-text-label-family);
      letter-spacing: var(--ui-text-label-tracking);
      color: var(--ui-text-muted);
    }

    .stat__hint {
      display: inline-flex;
      color: var(--ui-text-muted);
      cursor: help;
    }

    .stat__hint mat-icon {
      font-size: var(--ui-icon-xs);
      inline-size: var(--ui-icon-xs);
      block-size: var(--ui-icon-xs);
    }

    .stat__value {
      font: var(--ui-text-numeral-weight) var(--ui-text-numeral-size) / var(--ui-text-numeral-line)
        var(--ui-text-numeral-family);
      margin-block-start: var(--ui-space-2);
      color: var(--ui-text);
    }

    /* Tone is for the value only. A coloured label would compete with it. */
    .stat[data-tone='success'] .stat__value {
      color: var(--ui-status-success-on-soft);
    }

    .stat[data-tone='warning'] .stat__value {
      color: var(--ui-status-warning-on-soft);
    }

    .stat[data-tone='danger'] .stat__value {
      color: var(--ui-status-danger-on-soft);
    }

    .stat__trend {
      display: flex;
      align-items: center;
      gap: var(--ui-space-1);
      margin-block-start: var(--ui-space-2);
      font: var(--ui-text-caption-weight) var(--ui-text-caption-size) / var(--ui-text-caption-line)
        var(--ui-text-caption-family);
      color: var(--ui-text-muted);
    }

    .stat__trend mat-icon {
      font-size: var(--ui-icon-sm);
      inline-size: var(--ui-icon-sm);
      block-size: var(--ui-icon-sm);
    }

    .stat__trend[data-direction='up'] {
      color: var(--ui-status-success-on-soft);
    }

    .stat__trend[data-direction='down'] {
      color: var(--ui-status-danger-on-soft);
    }

    .stat__trend-label {
      color: var(--ui-text-muted);
    }

    @include bp.below(md) {
      .stat {
        padding-inline-end: 0;
        border-inline-end: none;
      }
    }
  `,
})
export class UiStat {
  /** What the figure measures. */
  readonly label = input.required<string>();

  /** The formatted figure. Format before passing it in, not here. */
  readonly value = input.required<string | number>();

  /** Supplementary detail behind the info affordance. */
  readonly hint = input<string>();

  /** Tints the value. Omit for a neutral figure. */
  readonly tone = input<'neutral' | 'success' | 'warning' | 'danger'>('neutral');

  /** Signed change, e.g. "+12%" or "3 pending". */
  readonly trend = input<string>();

  /** Direction of the trend. Sets both the arrow and the colour. */
  readonly trendDirection = input<'up' | 'down' | 'flat'>('flat');

  /** Context for the trend, e.g. "vs last cycle". Always pair with `trend`. */
  readonly trendLabel = input<string>();

  protected trendIcon(): string {
    return this.trendDirection() === 'up'
      ? 'trending_up'
      : this.trendDirection() === 'down'
        ? 'trending_down'
        : 'trending_flat';
  }
}
