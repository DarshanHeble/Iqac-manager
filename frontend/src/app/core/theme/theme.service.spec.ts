import { TestBed } from '@angular/core/testing';

import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-bs-theme');
    TestBed.configureTestingModule({});
  });

  afterEach(() => {
    localStorage.clear();
  });

  function service(): ThemeService {
    return TestBed.inject(ThemeService);
  }

  it('defaults to light when nothing is stored', () => {
    expect(service().theme()).toBe('light');
  });

  it('reflects the theme onto the document element', () => {
    const theme = service();
    theme.set('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');

    theme.set('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('also writes data-bs-theme for legacy template compatibility', () => {
    const theme = service();
    theme.set('dark');
    expect(document.documentElement.getAttribute('data-bs-theme')).toBe('dark');
  });

  it('persists the choice so a reload does not flash the wrong theme', () => {
    service().set('dark');
    expect(localStorage.getItem('theme')).toBe('dark');
  });

  it('toggles between themes', () => {
    const theme = service();
    theme.toggle();
    expect(theme.theme()).toBe('dark');
    theme.toggle();
    expect(theme.theme()).toBe('light');
  });

  it('tracks isDark consistently with theme', () => {
    const theme = service();
    theme.set('dark');
    expect(theme.isDark()).toBe(true);
    theme.set('light');
    expect(theme.isDark()).toBe(false);
  });

  it('reads a stored theme on construction', () => {
    localStorage.setItem('theme', 'dark');
    expect(service().theme()).toBe('dark');
  });

  it('ignores an unrecognised stored value', () => {
    localStorage.setItem('theme', 'sepia');
    expect(service().theme()).toBe('light');
  });
});
