import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * A small status or category label.
 *
 * The one element allowed to be fully round: a pill reads as a marker rather
 * than a container, which is what distinguishes it from the flat cards and
 * panels around it.
 *
 * Colour is chosen by `tone`, never by passing a hex value. That keeps the
 * light/dark pair correct for free — each tone resolves to a different
 * foreground and background in each theme.
 */
@Component({
  selector: 'ui-badge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="badge" [class]="'badge--' + tone()" [class.badge--dot]="dot()">
      @if (dot()) {
        <span class="badge__dot" aria-hidden="true"></span>
      }
      <ng-content />
    </span>
  `,
  styles: `
    :host {
      display: inline-flex;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: var(--ui-space-2);
      padding-inline: var(--ui-space-2);
      padding-block: 0 var(--ui-space-1);
      border-radius: var(--ui-radius-pill);
      font: var(--ui-text-label-weight) var(--ui-text-label-size) / var(--ui-text-label-line)
        var(--ui-text-label-family);
      letter-spacing: var(--ui-text-label-tracking);
      white-space: nowrap;
      /* Tinted background + a hairline of the same hue, rather than a solid fill.
         Solid pills at status weight would dominate a page of records. */
      background: var(--ui-badge-bg);
      color: var(--ui-badge-fg);
      box-shadow: inset 0 0 0 1px var(--ui-badge-border);
    }

    .badge__dot {
      inline-size: 6px;
      block-size: 6px;
      border-radius: var(--ui-radius-pill);
      background: var(--ui-badge-fg);
      flex-shrink: 0;
    }

    /* Tones map to the status token set emitted in _tokens.scss. */
    .badge--neutral {
      --ui-badge-bg: var(--ui-surface-muted);
      --ui-badge-fg: var(--ui-text-muted);
      --ui-badge-border: var(--ui-border);
    }

    .badge--primary {
      --ui-badge-bg: var(--ui-primary-container);
      --ui-badge-fg: var(--ui-on-primary-container);
      --ui-badge-border: transparent;
    }

    .badge--success {
      --ui-badge-bg: var(--ui-status-success-soft);
      --ui-badge-fg: var(--ui-status-success-on-soft);
      --ui-badge-border: var(--ui-status-success-border);
    }

    .badge--warning {
      --ui-badge-bg: var(--ui-status-warning-soft);
      --ui-badge-fg: var(--ui-status-warning-on-soft);
      --ui-badge-border: var(--ui-status-warning-border);
    }

    .badge--danger {
      --ui-badge-bg: var(--ui-status-danger-soft);
      --ui-badge-fg: var(--ui-status-danger-on-soft);
      --ui-badge-border: var(--ui-status-danger-border);
    }

    .badge--info {
      --ui-badge-bg: var(--ui-status-info-soft);
      --ui-badge-fg: var(--ui-status-info-on-soft);
      --ui-badge-border: var(--ui-status-info-border);
    }
  `,
})
export class UiBadge {
  /** Semantic tone. Drives colour only; never pass a colour directly. */
  readonly tone = input<'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'>(
    'neutral',
  );

  /** Show a leading dot. Useful when the badge sits next to other content. */
  readonly dot = input(false);
}
