import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';

import { UiBadge } from './badge';
import { UiCard } from './card';
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

    it('does not render an action slot when nothing is projected', async () => {
      const host = TestBed.createComponent(UiCard);
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      expect(el.querySelector('.card__actions')).toBeNull();
    });
  });

  describe('UiRecordRow', () => {
    it('exposes the tone as data so the status rule can be read from the DOM', async () => {
      const host = TestBed.createComponent(UiRecordRow);
      host.componentRef.setInput('tone', 'warning');
      host.detectChanges();
      const el = host.nativeElement as HTMLElement;
      expect(el.querySelector('.record')?.getAttribute('data-tone')).toBe('warning');
    });
  });

  describe('UiSection', () => {
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
  });
});
