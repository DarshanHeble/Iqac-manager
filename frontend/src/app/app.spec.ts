import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

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
});
