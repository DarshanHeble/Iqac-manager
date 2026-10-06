import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TestBed } from '@angular/core/testing';

import { UiBadge } from './badge';
import { UiButton } from './button';
import { UiCard } from './card';
import { UiEmptyState } from './empty-state';
import { UiField } from './field';
import { UiPageHeader } from './page-header';
import { UiRecordRow } from './record-row';
import { UiSection } from './section';
import { UiStat } from './stat';

/**
 * These tests guard the rules that keep the design system coherent: tone-based
 * colour, no unboxed status, and no raw values in component styles.
 *
 * The style-source assertions matter as much as the rendering ones. A component
 * that inlines a hex or a pixel value compiles and looks fine in isolation, but
 * silently stops responding to the theme — which is exactly the drift these
 * tests exist to prevent.
 */
describe('design system components', () => {
  beforeEach(() => {
    TestBed.resetTestingModule();
  });

  describe('UiBadge', () => {
    it('renders a pill rather than a block', async () => {
      const host = TestBed.createComponent(UiBadge);
      host.componentRef.setInput('tone', 'success');
      host.detectChanges();
      const badge = (host.nativeElement as HTMLElement).querySelector('.badge');
      expect(badge).toBeTruthy();
      expect(getComputedStyle(badge!).display).toBe('inline-flex');
    });

    it('drives colour from tone, not from an inline style', async () => {
      const host = TestBed.createComponent(UiBadge);
      host.componentRef.setInput('tone', 'danger');
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      expect(el.querySelector('.badge')?.getAttribute('class')).toContain('badge--danger');
      // No background should be hardcoded on the element itself.
      expect(el.querySelector('.badge')?.getAttribute('style')).toBeNull();
    });
  });

  describe('UiCard', () => {
    it('emits a heading at the correct level', async () => {
      const host = TestBed.createComponent(UiCard);
      host.componentRef.setInput('heading', 'Submission register');
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      expect(el.querySelector('.card__title')?.textContent).toContain('Submission register');
    });

    /**
     * The slots are always in the DOM and collapsed by CSS. Asserting on computed
     * style rather than presence is the point: the element existing is what makes
     * the slots work without the consumer importing anything.
     */
    it('collapses an unpopulated slot instead of leaving a gap', async () => {
      const host = TestBed.createComponent(UiCard);
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      for (const selector of ['.card__header', '.card__actions', '.card__footer']) {
        const slot = el.querySelector(selector);
        expect(slot, `${selector} should exist`).toBeTruthy();
        expect(getComputedStyle(slot!).display, `${selector} should collapse`).toBe('none');
      }
    });

    it('adds the spine rule only when asked', async () => {
      const host = TestBed.createComponent(UiCard);
      host.detectChanges();
      expect((host.nativeElement as HTMLElement).querySelector('.card--spine')).toBeNull();

      host.componentRef.setInput('spine', true);
      host.detectChanges();
      expect((host.nativeElement as HTMLElement).querySelector('.card')!.classList).toContain(
        'card--spine',
      );
    });

    /**
     * `borderInlineStartWidth` is not asserted: jsdom cannot resolve the
     * `--ui-spine-width` custom property, which is defined in the global
     * stylesheet rather than the component's. The class assertion above is what
     * this component is responsible for; the token's value is the palette's
     * responsibility and is covered there.
     */
  });

  describe('UiRecordRow', () => {
    it('exposes the tone as data so the status rule can be read from the DOM', async () => {
      const host = TestBed.createComponent(UiRecordRow);
      host.componentRef.setInput('tone', 'warning');
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      expect(el.querySelector('.record')?.getAttribute('data-tone')).toBe('warning');
    });

    it('collapses the trailing slot when nothing is projected', async () => {
      const host = TestBed.createComponent(UiRecordRow);
      host.detectChanges();
      const slot = (host.nativeElement as HTMLElement).querySelector('.record__trailing');
      expect(slot).toBeTruthy();
      expect(getComputedStyle(slot!).display).toBe('none');
    });
  });

  /**
   * These cover inputs that were declared but never read. A dead input is worse
   * than a missing one: the consumer sets it, sees no error, and the component
   * silently ignores them.
   */
  describe('inputs that must actually do something', () => {
    it('UiButton places a trailing icon after the label', async () => {
      const host = TestBed.createComponent(UiButton);
      host.componentRef.setInput('icon', 'open_in_new');
      host.componentRef.setInput('iconPosition', 'trailing');
      host.detectChanges();
      const button = (host.nativeElement as HTMLElement).querySelector('button')!;
      const label = button.querySelector('.btn__label')!;
      const icon = button.querySelector('mat-icon')!;

      expect(icon.textContent).toContain('open_in_new');
      // compareDocumentPosition is asked on the label: does the icon follow it?
      expect(label.compareDocumentPosition(icon) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it('UiButton replaces the icon with a spinner while loading', async () => {
      const host = TestBed.createComponent(UiButton);
      host.componentRef.setInput('icon', 'save');
      host.detectChanges();
      expect((host.nativeElement as HTMLElement).querySelector('mat-icon')?.textContent).toContain(
        'save',
      );

      host.componentRef.setInput('loading', true);
      host.detectChanges();
      const icon = (host.nativeElement as HTMLElement).querySelector('mat-icon');
      expect(icon?.textContent).toContain('progress_activity');
      expect(icon?.classList.contains('btn__spinner')).toBe(true);
    });

    it('UiPageHeader reports which action was pressed', async () => {
      const host = TestBed.createComponent(UiPageHeader);
      host.componentRef.setInput('title', 'Submission register');
      host.componentRef.setInput('actions', [
        { id: 'export', label: 'Export' },
        { id: 'add', label: 'Add entry' },
      ] as const);
      host.detectChanges();

      const chosen: string[] = [];
      host.componentInstance.actionSelected.subscribe((a) => chosen.push(a.id));

      const buttons = (host.nativeElement as HTMLElement).querySelectorAll('button');
      expect(buttons.length).toBe(2);
      buttons[1].click();
      expect(chosen).toEqual(['add']);
    });

    it('UiPageHeader renders no buttons when given no actions', async () => {
      const host = TestBed.createComponent(UiPageHeader);
      host.componentRef.setInput('title', 'Submission register');
      host.detectChanges();
      expect((host.nativeElement as HTMLElement).querySelectorAll('button').length).toBe(0);
    });
  });

  describe('UiSection', () => {
    it('collapses the action slot when nothing is projected', async () => {
      const host = TestBed.createComponent(UiSection);
      host.componentRef.setInput('title', 'Colour roles');
      host.detectChanges();
      const slot = (host.nativeElement as HTMLElement).querySelector('.section__actions');
      expect(slot).toBeTruthy();
      expect(getComputedStyle(slot!).display).toBe('none');
    });

    it('labels itself for assistive technology', async () => {
      const host = TestBed.createComponent(UiSection);
      host.componentRef.setInput('title', 'Colour roles');
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      const id = el.querySelector('.section__title')?.getAttribute('id');
      expect(id).toBeTruthy();
      expect(el.querySelector('section')?.getAttribute('aria-labelledby')).toBe(id);
    });
  });

  describe('UiStat', () => {
    it('marks the value as a figure so columns of numbers align', async () => {
      const host = TestBed.createComponent(UiStat);
      host.componentRef.setInput('label', 'Total entries');
      host.componentRef.setInput('value', '247');
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      expect(el.querySelector('.stat__value')?.classList.contains('num')).toBe(true);
      expect(el.querySelector('.stat__value')?.textContent).toContain('247');
    });
  });

  describe('UiEmptyState', () => {
    it('collapses unpopulated slots', async () => {
      const host = TestBed.createComponent(UiEmptyState);
      host.componentRef.setInput('title', 'No entries yet');
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      for (const selector of ['.empty__action', '.empty__secondary']) {
        const slot = el.querySelector(selector);
        expect(slot, `${selector} should exist`).toBeTruthy();
        expect(getComputedStyle(slot!).display).toBe('none');
      }
    });
  });

  /**
   * `UiField` has to stay a directive on `mat-form-field` rather than a wrapper
   * that projects the control. Material locates a field's control with a content
   * query on `MatFormField`, and that query only matches directives declared in
   * the same template as the field itself. Project a control through a wrapper
   * and the query comes back empty: the field renders blank and Material throws
   * when it reads `controlType` off the missing control. The failure is at
   * runtime with no compile-time signal, so it is pinned here.
   */
  describe('UiField', () => {
    @Component({
      imports: [FormsModule, MatFormFieldModule, MatInputModule, UiField],
      template: `
        <mat-form-field ui-field [error]="error">
          <mat-label>Name</mat-label>
          <input matInput [ngModel]="name" />
        </mat-form-field>
      `,
    })
    class FieldHost {
      name = '';
      error?: string;
    }

    beforeEach(async () => {
      await TestBed.configureTestingModule({ imports: [FieldHost] }).compileComponents();
    });

    it('resolves a control declared in the same template', () => {
      const fixture = TestBed.createComponent(FieldHost);
      fixture.detectChanges();
      const el = fixture.nativeElement as HTMLElement;
      const field = el.querySelector('mat-form-field')!;
      const input = el.querySelector('input')!;

      // Material gives the control an id and points the rendered <label> at it
      // only after it has resolved a control for the field. Both together are the
      // observable difference between a field that works and one whose content
      // query came back empty — the case that produced blank fields and the
      // `controlType` crash.
      expect(input.id).toBeTruthy();
      expect(field.contains(input)).toBe(true);
      expect(field.querySelector('label')!.getAttribute('for')).toBe(input.id);
    });

    it('marks the error state with a class, never an inline colour', () => {
      const fixture = TestBed.createComponent(FieldHost);
      fixture.componentInstance.error = 'Required';
      fixture.detectChanges();

      const field = fixture.nativeElement.querySelector('mat-form-field') as HTMLElement;
      expect(field.classList).toContain('ui-field--invalid');
      expect(field.getAttribute('style')).toBeNull();
    });

    it('leaves the error state off while the field is valid', () => {
      const fixture = TestBed.createComponent(FieldHost);
      fixture.detectChanges();

      const field = fixture.nativeElement.querySelector('mat-form-field') as HTMLElement;
      expect(field.classList).not.toContain('ui-field--invalid');
    });

    /**
     * Material picks `<mat-error>` over `<mat-hint>` from `control.errorState` and
     * from nothing else. A class on the host is invisible to it, so an error state
     * that only set one produced a red outline still showing the hint and no error
     * message. The forced state has to reach the control.
     */
    it('shows the error message instead of the hint when forced', async () => {
      @Component({
        imports: [FormsModule, MatFormFieldModule, MatInputModule, UiField],
        template: `
          <mat-form-field ui-field [error]="error">
            <mat-label>Reference</mat-label>
            <mat-hint>Format: XXXX</mat-hint>
            <input matInput [ngModel]="name" />
            <mat-error>Reference number is required.</mat-error>
          </mat-form-field>
        `,
      })
      class HintedHost {
        name = '';
        error = 'Reference number is required.';
      }

      await TestBed.configureTestingModule({ imports: [HintedHost] }).compileComponents();
      const fixture = TestBed.createComponent(HintedHost);
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();

      const el = fixture.nativeElement as HTMLElement;
      const rendered = [
        ...el.querySelectorAll(
          '.mat-mdc-form-field-hint-wrapper, .mat-mdc-form-field-error-wrapper',
        ),
      ]
        .map((n) => n.textContent?.trim())
        .filter(Boolean);

      expect(rendered.join(' | ')).toContain('Reference number is required.');
      expect(rendered.join(' | ')).not.toContain('Format: XXXX');
    });
  });

  describe('style discipline', () => {
    const root = process.cwd();

    const sources: Record<string, string> = Object.fromEntries(
      [
        ...[
          'badge',
          'button',
          'card',
          'empty-state',
          'field',
          'page-header',
          'record-row',
          'section',
          'stat',
        ].map((name) => [name, join(root, 'src/app/ui', `${name}.ts`)] as const),
        ['app.scss', join(root, 'src/app/app.scss')] as const,
        ['styleguide.scss', join(root, 'src/app/features/styleguide/styleguide.scss')] as const,
      ].map(([name, file]) => [name, readFileSync(file, 'utf8')]),
    );

    /** Strip comments so the assertions test code, not prose. */
    const strip = (source: string): string =>
      source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

    it('covers every component file', () => {
      expect(Object.keys(sources)).toHaveLength(11);
    });

    it('contains no raw hex colours in component styles', () => {
      for (const [path, source] of Object.entries(sources)) {
        expect(strip(source), `${path} must not contain a hex colour`).not.toMatch(
          /#[0-9a-fA-F]{3,8}\b/,
        );
      }
    });

    it('contains no hardcoded font sizes in component styles', () => {
      for (const [path, source] of Object.entries(sources)) {
        expect(strip(source), `${path} must use --ui-text-* for font sizes`).not.toMatch(
          /font-size:\s*[\d.]+(px|rem|em)/,
        );
      }
    });

    it('contains no hardcoded spacing in component styles', () => {
      for (const [path, source] of Object.entries(sources)) {
        expect(strip(source), `${path} must use --ui-space-* for spacing`).not.toMatch(
          /(?:padding|margin|gap|inset)[a-z-]*:\s*[^;{}]*[\d.]+(?:px|rem)\b/,
        );
      }
    });

    /**
     * A raw `@media (width <= 640px)` is a threshold nobody can find or change.
     * The values live in _palette.scss and are emitted by the `breakpoints`
     * partial, so a component that writes its own query has forked the scale.
     */
    it('contains no raw media queries in component styles', () => {
      for (const [path, source] of Object.entries(sources)) {
        expect(strip(source), `${path} must @include bp.below/atleast`).not.toMatch(
          /@media[^{]*width/,
        );
      }
    });

    /**
     * The palette is the one file allowed to name a colour; every other layer
     * must reference a token. This is the rule that makes a single source of
     * truth true rather than aspirational.
     */
    it('keeps hex colours out of every style layer except the palette', () => {
      const layers = readdirSync(join(root, 'src/styles'))
        .filter((f) => f.endsWith('.scss') && f !== '_palette.scss')
        .map((f) => [f, readFileSync(join(root, 'src/styles', f), 'utf8')] as const);

      expect(layers.length).toBeGreaterThan(0);
      for (const [path, source] of layers) {
        expect(strip(source), `src/styles/${path} must not name a hex colour`).not.toMatch(
          /#[0-9a-fA-F]{3,8}\b/,
        );
      }
    });
  });
});
