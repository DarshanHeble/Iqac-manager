import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatCheckboxModule } from '@angular/material/checkbox';

import { ThemeService } from '../../core/theme/theme.service';
import {
  UiBadge,
  UiButton,
  UiCard,
  UiEmptyState,
  UiField,
  UiPageHeader,
  UiRecordRow,
  UiSection,
  UiStat,
} from '../../ui';

/**
 * The design system, rendered.
 *
 * This exists so the design system can be checked rather than described. A token
 * table in a document proves nothing; seeing the same page in light and dark, on
 * a real background, at real sizes, is the only way to catch a token that was
 * never wired up or a contrast pair that fails in one theme.
 *
 * Switch to `data-theme="dark"` and everything on this page must change
 * together. Anything that stays put is a bug in _semantic.scss.
 *
 * Not a test and not documentation-only: it is the same code a feature screen
 * would use, so it also serves as the reference implementation.
 */
@Component({
  selector: 'app-styleguide',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    UiBadge,
    UiButton,
    UiCard,
    UiEmptyState,
    UiField,
    UiPageHeader,
    UiRecordRow,
    UiSection,
    UiStat,
  ],
  templateUrl: './styleguide.html',
  styleUrl: './styleguide.scss',
})
export class Styleguide {
  protected readonly theme = inject(ThemeService);

  protected sampleName = 'Dr. A. Ramachandran';
  protected sampleDept = 'Department of Computer Applications';
  protected sampleDate = '12 March';
  protected selectedDept = 'Computer Applications';

  protected readonly departments = [
    'Computer Applications',
    'Mathematics',
    'Physics',
    'Library Science',
  ];

  protected readonly statusTones = [
    'neutral',
    'primary',
    'success',
    'warning',
    'danger',
    'info',
  ] as const;

  protected readonly colorRoles = [
    { token: '--ui-primary', use: 'Primary action, brand navy' },
    { token: '--ui-on-primary', use: 'Text on primary' },
    { token: '--ui-primary-container', use: 'Tinted primary background' },
    { token: '--ui-accent', use: 'Tertiary accent' },
    { token: '--ui-bg', use: 'Page background' },
    { token: '--ui-surface-raised', use: 'Panels, cards' },
    { token: '--ui-surface-sunken', use: 'Table stripes, wells' },
    { token: '--ui-text', use: 'Body text' },
    { token: '--ui-text-muted', use: 'Secondary text' },
    { token: '--ui-border', use: 'Hairlines' },
    { token: '--ui-border-strong', use: 'Control outlines' },
    { token: '--ui-danger', use: 'Errors, destructive' },
  ];

  protected readonly typeRoles = [
    { role: 'display-lg', sample: 'Annual Quality Assurance Report' },
    { role: 'h1', sample: 'Faculty Worklog' },
    { role: 'h2', sample: 'Department Overview' },
    { role: 'h3', sample: 'Submission History' },
    { role: 'h4', sample: 'Pending Entries' },
    { role: 'h5', sample: 'Cycle 2025–26' },
    { role: 'h6', sample: 'Reviewed on 12 March' },
    { role: 'lead', sample: 'Collect and verify activity records for the current cycle.' },
    { role: 'body', sample: 'Each entry is reviewed by the coordinator before final submission.' },
    { role: 'body-sm', sample: 'Last updated 12 March 2026 at 14:20.' },
    { role: 'caption', sample: 'Institute Reference No. IQAC/2025/041' },
    { role: 'label', sample: 'Academic Year' },
    { role: 'overline', sample: 'Section Label' },
    { role: 'quote', sample: 'Quality assurance is a continuous process, not an annual exercise.' },
    { role: 'code', sample: 'GET /api/departments' },
    { role: 'numeral', sample: '247' },
  ];

  protected readonly typeClasses = [
    'text-display-lg',
    'text-h1',
    'text-h2',
    'text-h3',
    'text-h4',
    'text-h5',
    'text-h6',
    'text-lead',
    'text-body',
    'text-body-sm',
    'text-caption',
    'text-label',
    'text-overline',
    'text-numeral',
  ];
}
