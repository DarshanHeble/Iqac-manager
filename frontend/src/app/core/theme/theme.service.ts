import { Injectable, computed, effect, signal } from '@angular/core';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme';

/**
 * Owns the active theme.
 *
 * The contract is a `data-theme` attribute on <html>. Every `--ui-*` token is
 * scoped to `[data-theme='light']` or `[data-theme='dark']` in _tokens.scss, so
 * switching themes is one attribute change and the entire UI follows. There is
 * no per-component theme state and no re-rendering involved.
 *
 * `data-bs-theme` is also written for compatibility with the legacy Flask
 * templates and anything expecting Bootstrap 5.3's native dark mode. The Angular
 * app does not depend on it — the legacy templates only ever set `data-theme`.
 *
 * index.html applies the stored theme before first paint, so there is no flash
 * on load. This service only needs to keep the DOM in sync afterwards.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly current = signal<Theme>(this.readStoredTheme());

  /** The active theme. Writing to this updates the DOM and localStorage. */
  readonly theme = this.current.asReadonly();

  /** True when dark, for template branching and mat-icon ligatures. */
  readonly isDark = computed(() => this.current() === 'dark');

  private systemQuery: MediaQueryList | null = null;

  constructor() {
    // The effect reconciles the DOM whenever the signal changes by any route
    // (set, toggle, the OS listener). Reading the signal inside the effect is
    // what registers the dependency.
    effect(() => this.commit(this.current()));
  }

  /** Switch to an explicit theme. */
  set(theme: Theme): void {
    this.change(theme);
  }

  /** Switch to whichever theme is not active. */
  toggle(): void {
    this.change(this.current() === 'dark' ? 'light' : 'dark');
  }

  /**
   * Update the signal and write through to the DOM and storage synchronously.
   *
   * The effect reconciles the DOM for any change that reaches the signal by
   * another route, so it is the single source of truth. Writing through here as
   * well is what lets `set()` and `toggle()` be observable the instant they
   * return — which the tests and the pre-paint flash both depend on. The write
   * is idempotent, so the effect running afterwards changes nothing.
   */
  private change(theme: Theme): void {
    this.current.set(theme);
    this.commit(theme);
  }

  private commit(theme: Theme): void {
    this.apply(theme);

    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Private browsing or disabled storage: the theme still applies for this
      // session, it just will not be remembered.
    }
  }

  /**
   * Adopt the OS preference once.
   *
   * This deliberately does not keep listening: after an explicit choice, the
   * user's choice should win on reload rather than being overridden by whatever
   * the OS says that day. `watchSystemPreference` is available for a screen that
   * explicitly offers live OS tracking.
   */
  useSystemPreference(): void {
    this.change(this.systemTheme());
  }

  /** Follow the OS preference live, until `stopWatchingSystemPreference`. */
  watchSystemPreference(): void {
    this.systemQuery?.removeEventListener('change', this.onSystemChange);
    this.systemQuery = window.matchMedia?.('(prefers-color-scheme: dark)') ?? null;
    this.systemQuery?.addEventListener('change', this.onSystemChange);
  }

  /** Stop following the OS preference. */
  stopWatchingSystemPreference(): void {
    this.systemQuery?.removeEventListener('change', this.onSystemChange);
    this.systemQuery = null;
  }

  private readonly onSystemChange = (event: MediaQueryListEvent): void => {
    this.change(event.matches ? 'dark' : 'light');
  };

  private systemTheme(): Theme {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  private apply(theme: Theme): void {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-bs-theme', theme);
  }

  /**
   * Read the stored theme, defaulting to light. Never throws: localStorage is
   * unavailable in some privacy modes and SSR/test contexts.
   */
  private readStoredTheme(): Theme {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored === 'dark' || stored === 'light' ? stored : 'light';
    } catch {
      return 'light';
    }
  }
}
