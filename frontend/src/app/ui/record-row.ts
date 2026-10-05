import { ChangeDetectionStrategy, Component, contentChild, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { UiBadge } from './badge';

export type RecordTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

/** Trailing slot: actions, counts, or a link out of the row. */
@Component({
  selector: '[ui-record-trailing]',
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UiRecordRowTrailing {}

/**
 * One row in a register: an entity plus the state it is in.
 *
 * This is the component the legacy app effectively reimplemented as a `<tr>`
 * with a left border colour on every screen. The rule is the point — a coloured
 * leading edge lets you scan a column of records for the ones needing attention
 * without reading a single word, which is the whole job of a review screen.
 *
 * `tone` is deliberately narrow. If a screen needs a colour that is not one of
 * the four status values, that is a signal the status model itself should grow,
 * not that a hex should be passed in.
 */
@Component({
  selector: 'ui-record-row',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, UiBadge],
  template: `
    <article class="record" [attr.data-tone]="tone()">
      <div class="record__main">
        <div class="record__heading">
          <h3 class="record__title">
            <ng-content select="[recordTitle]" />
          </h3>

          @if (status(); as value) {
            <ui-badge [tone]="tone()" [dot]="showDot()">{{ value }}</ui-badge>
          }
        </div>

        <p class="record__meta">
          <ng-content select="[recordMeta]" />
        </p>

        <div class="record__detail">
          <ng-content select="[recordDetail]" />
        </div>
      </div>

      @if (trailingSlot()) {
        <div class="record__trailing">
          <ng-content select="[ui-record-trailing]" />
        </div>
      }
    </article>
  `,
  styles: `
    @use 'typography' as type;

    .record {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: var(--ui-space-4);
      padding: var(--ui-space-4) var(--ui-space-5);
      background: var(--ui-surface-raised);
      border: var(--ui-rule-width) solid var(--ui-border);
      /* The status rule. Colour is carried by the leading edge, not a tinted
         background — a wash of colour behind every row would make the page
         unreadable at length. */
      border-inline-start: var(--ui-spine-width) solid var(--ui-rule-color);
      border-radius: var(--ui-radius-md);
    }

    .record[data-tone='success'] {
      --ui-rule-color: var(--ui-status-success-border);
    }

    .record[data-tone='warning'] {
      --ui-rule-color: var(--ui-status-warning-border);
    }

    .record[data-tone='danger'] {
      --ui-rule-color: var(--ui-status-danger-border);
    }

    .record[data-tone='info'] {
      --ui-rule-color: var(--ui-status-info-border);
    }

    .record[data-tone='neutral'] {
      /* Neutral rows get the brand navy, not grey: the rule is structural, and
         grey would read as "disabled" rather than "no status". */
      --ui-rule-color: var(--ui-primary);
    }

    .record__main {
      min-inline-size: 0;
      flex: 1;
    }

    .record__heading {
      display: flex;
      align-items: center;
      gap: var(--ui-space-3);
      flex-wrap: wrap;
    }

    .record__title {
      @include type.heading(h4);
      min-inline-size: 0;
    }

    .record__meta {
      @include type.text-role(body-sm);
      color: var(--ui-text-muted);
      margin-block-start: var(--ui-space-1);
    }

    .record__detail {
      @include type.text-role(body-sm);
      margin-block-start: var(--ui-space-2);
      max-inline-size: var(--ui-measure);
    }

    .record__detail:empty {
      display: none;
    }

    .record__trailing {
      display: flex;
      align-items: center;
      gap: var(--ui-space-2);
      flex-shrink: 0;
    }

    @media (width <= 640px) {
      .record {
        flex-direction: column;
      }
    }
  `,
})
export class UiRecordRow {
  /** Current state, shown as a badge. Omit for a row with no status. */
  readonly status = input<string>();

  /** Which status colour the leading rule takes. */
  readonly tone = input<RecordTone>('neutral');

  /** Show a dot in the badge. Use when the rule alone is too subtle to read. */
  readonly showDot = input(false);

  protected readonly trailingSlot = contentChild(UiRecordRowTrailing);
}
