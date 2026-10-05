import { InjectionToken, inject } from '@angular/core';

/**
 * Base path for every backend call.
 *
 * The Angular app and the Flask API are served from the same origin: in
 * development the dev server proxies `/api` to Flask (see proxy.conf.json),
 * and in production Flask serves the compiled Angular bundle. Keeping the base
 * path relative is what lets the existing Flask session cookie work without any
 * CORS configuration or JWT migration.
 */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL', {
  providedIn: 'root',
  factory: () => '/api',
});

/** Convenience helper for building API URLs. */
export function apiUrl(path: string): string {
  const base = inject(API_BASE_URL);
  return `${base}/${path.replace(/^\//, '')}`;
}