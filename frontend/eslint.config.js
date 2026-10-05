// @ts-check
const eslint = require('@eslint/js');
const { defineConfig } = require('eslint/config');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');
const prettier = require('eslint-config-prettier');

module.exports = defineConfig([
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      tseslint.configs.recommended,
      tseslint.configs.stylistic,
      angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      '@angular-eslint/directive-selector': [
        'error',
        {
          type: 'attribute',
          prefix: 'app',
          style: 'camelCase',
        },
      ],
      '@angular-eslint/component-selector': [
        'error',
        {
          type: 'element',
          prefix: 'app',
          style: 'kebab-case',
        },
      ],
    },
  },
  {
    // The design system is a separate namespace from feature components.
    //
    // Two deliberate deviations from the app-wide rules:
    //   prefix `ui`  — keeps `ui-*` recognisable as design-system surface
    //                  wherever it appears, and makes "is this ours or the app's?"
    //                  answerable from the tag name alone.
    //   attributes   — the projection slots (`[cardActions]`, `[recordTitle]`,
    //                  `[emptyAction]`) are markers, not components with
    //                  behaviour. Angular has no built-in content-projection
    //                  detection, so each slot is a zero-template attribute
    //                  component queried with contentChild().
    files: ['src/app/ui/**/*.ts'],
    rules: {
      '@angular-eslint/component-selector': [
        'error',
        {
          type: ['element', 'attribute'],
          prefix: 'ui',
          style: 'kebab-case',
        },
      ],
      '@angular-eslint/directive-selector': [
        'error',
        {
          type: 'attribute',
          prefix: 'ui',
          style: 'kebab-case',
        },
      ],
    },
  },
  {
    files: ['**/*.html'],
    extends: [angular.configs.templateRecommended, angular.configs.templateAccessibility],
    rules: {},
  },
  prettier,
]);
