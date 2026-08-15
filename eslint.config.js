'use strict';

const js = require('@eslint/js');
const globals = require('globals');
const prettier = require('eslint-config-prettier');

module.exports = [
  { ignores: ['node_modules/**', 'output/**', 'data/**', '.venv/**'] },
  js.configs.recommended,
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'script',
      globals: {
        ...globals.browser,
        ...globals.node,
        LightweightCharts: 'readonly',
      },
    },
    rules: {
      // The codebase intentionally shadows these names (e.g. `_t`, `model`).
      'no-redeclare': 'off',
      'no-global-assign': 'off',
    },
  },
  prettier,
];
