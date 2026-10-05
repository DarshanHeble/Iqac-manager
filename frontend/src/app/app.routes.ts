import { Routes } from '@angular/router';

/**
 * Feature routes. Added one screen at a time as vertical slices, so every entry
 * here maps to a migrated Flask screen.
 *
 * `loadComponent` is used throughout: each screen becomes its own chunk, and
 * nothing is eagerly pulled into the initial bundle. There is no eager-load
 * barrel anywhere in the app for this reason.
 */
export const routes: Routes = [
  {
    path: 'styleguide',
    title: 'Style Guide · IQAC',
    loadComponent: () => import('./features/styleguide/styleguide').then((m) => m.Styleguide),
  },

  // Everything else lands on the styleguide until the first real screen exists.
  { path: '', pathMatch: 'full', redirectTo: 'styleguide' },
  { path: '**', redirectTo: 'styleguide' },
];
