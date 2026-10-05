import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ThemeService } from './core/theme/theme.service';
import { UiBadge } from './ui';

/**
 * Application shell: the left rail, the top bar, and the routed outlet.
 *
 * The rail keeps the legacy dimensions (264px, 64px top bar) so the navigation
 * feels identical to the Flask app staff already use. The navy spine down its
 * leading edge is the one bold element on screen.
 *
 * Layout classes here (`.rail`, `.topbar`, `.content`) come from _layout.scss,
 * not from component styles: they are app-wide structure, so they belong in one
 * place rather than being restated by whichever component renders them.
 */
@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule, RouterLink, RouterLinkActive, RouterOutlet, UiBadge],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly theme = inject(ThemeService);
}
