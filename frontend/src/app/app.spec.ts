import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { App } from './app';
import { routes } from './app.routes';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes)],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('renders the app shell landmarks', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;

    // The shell is only usable if these three exist and are correctly labelled.
    expect(el.querySelector('nav[aria-label="Main"]')).toBeTruthy();
    expect(el.querySelector('main#main-content')).toBeTruthy();
    expect(el.querySelector('.skip-link')?.getAttribute('href')).toBe('#main-content');
  });

  it('exposes a single h1 per screen via the routed outlet', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;

    // The shell's own headings are h2 so the routed screen owns the h1.
    expect(el.querySelectorAll('h1').length).toBeLessThanOrEqual(1);
  });

  /**
   * Angular reports a mismatched root tag as NG05104 at runtime and renders a
   * blank page — no test failed, no build failed, and nothing in the console of a
   * component test points at the cause. The tag and the selector are parsed from
   * different files and nothing checks they agree, so it is checked here.
   */
  it('bootstraps the tag that index.html declares', () => {
    const html = readFileSync(join(process.cwd(), 'src/index.html'), 'utf8');
    const tag = html.match(/<([a-z][a-z0-9-]*-root)><\/\1>/i)?.[1];

    expect(tag, 'index.html should declare a single <*-root> element').toBeTruthy();
    expect((App as unknown as { ɵcmp: { selectors: string[][] } }).ɵcmp.selectors).toContainEqual([
      tag!,
    ]);
  });
});
