import { ChangeDetectionStrategy, Component, contentChild, input } from '@angular/core';

/** Marker for the card's action slot, e.g. an "Export" button. */
@Component({
  selector: '[ui-card-actions]',
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UiCardActions {}

/** Marker for the card's footer slot. */
@Component({
  selector: '[ui-card-footer]',
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UiCardFooter {}

/**
 * A flat content panel.
 *
 * Borders, not shadows. A shadow on every panel is the single clearest signal
 * of a generic template, and this app has a lot of panels — a page of stacked
 * shadowed cards would read as a marketing site rather than a register. Shadow
 * is reserved for things that genuinely float (menus, dialogs, the rail).
 *
 * The optional `spine` puts the signature 3px navy rule on the leading edge,
 * which is how a records system marks the start of an entry.
 */
@Component({
  selector: 'ui-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="card" [class.card--flush]="flush()" [class.card--raised]="raised()">
      @if (heading() || headingTight() || actionSlot()) {
        <header class="card__header">
          @if (heading()) {
            <h3 class="card__title">{{ heading() }}</h3>
          }
          @if (headingTight()) {
            <h4 class="card__title card__title--tight">{{ headingTight() }}</h4>
          }
          @if (actionSlot()) {
            <div class="card__actions">
              <ng-content select="[ui-card-actions]" />
            </div>
          }
        </header>
      }

      <div class="card__body" [class.card__body--flush]="flush()">
        <ng-content />
      </div>

      @if (footerSlot()) {
        <footer class="card__footer">
          <ng-content select="[ui-card-footer]" />
        </footer>
      }
    </section>
  `,
  styles: `
    @use 'typography' as type;

    :host {
      display: block;
      min-inline-size: 0;
    }

    .card {
      position: relative;
      background: var(--ui-surface-raised);
      border: var(--ui-rule-width) solid var(--ui-border);
      border-radius: var(--ui-radius-md);
      color: var(--ui-text);

      /* Collapse the header/footer radii so a flush card has clean edges. */
      overflow: hidden;
    }

    /* The spine. A border rather than a pseudo-element, so it sits under the
       content and never needs its own layout box. */
    .card--spine {
      border-inline-start: var(--ui-spine-width) solid var(--ui-primary);
    }

    .card--raised {
      /* Only for genuinely floating surfaces. */
      box-shadow: var(--ui-shadow-2);
    }

    .card__header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--ui-space-4);
      padding: var(--ui-space-4) var(--ui-space-5);
      border-block-end: var(--ui-rule-width) solid var(--ui-border);
      background: var(--ui-surface-raised);
    }

    .card__title {
      @include type.heading(h4);
      min-inline-size: 0;
    }

    /* One step down from the panel title, for the smaller nested case. */
    .card__title--tight {
      @include type.heading(h5);
    }

    .card__actions {
      display: flex;
      align-items: center;
      gap: var(--ui-space-2);
      flex-shrink: 0;
    }

    .card__body {
      padding: var(--ui-space-5);
    }

    .card__body--flush {
      padding: 0;
    }

    .card--flush .card__body {
      padding: 0;
    }

    .card__footer {
      display: flex;
      align-items: center;
      gap: var(--ui-space-3);
      padding: var(--ui-space-3) var(--ui-space-5);
      border-block-start: var(--ui-rule-width) solid var(--ui-border);
      background: var(--ui-surface-sunken);
    }
  `,
})
export class UiCard {
  /** Panel title at the h3 level. */
  readonly heading = input<string>();

  /** Panel title at the h4 level, for a card nested inside another. */
  readonly headingTight = input<string>();

  /** Remove body padding, so a table or list runs edge to edge. */
  readonly flush = input(false);

  /** Add the signature leading rule. */
  readonly spine = input(false);

  /** Opt in to elevation. Off by default. */
  readonly raised = input(false);

  protected readonly actionSlot = contentChild(UiCardActions);
  protected readonly footerSlot = contentChild(UiCardFooter);
}
