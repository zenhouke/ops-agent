import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'src-tauri/target'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'no-control-regex': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-refresh/only-export-components': ['warn', {
        allowConstantExport: true,
        allowExportNames: ['normalizeHexColor', 'useAppearance'],
      }],
    },
  },
  ...[
    { files: ['src/hooks/**/*.{ts,tsx}'], forbidden: ['**/components/**', '**/App', '**/App.*'] },
    { files: ['src/api/**/*.{ts,tsx}'], forbidden: ['**/components/**', '**/hooks/**', '**/App', '**/App.*'] },
    { files: ['src/utils/**/*.{ts,tsx}', 'src/types/**/*.{ts,tsx}'], forbidden: ['**/components/**', '**/hooks/**', '**/api/**', '**/App', '**/App.*'] },
  ].map(({ files, forbidden }) => ({
    files,
    rules: {
      'no-restricted-imports': ['error', { patterns: [{
        group: forbidden,
        message: 'Keep dependencies directed toward shared types, utilities and API clients; do not import upper layers.',
      }] }],
    },
  })),
);
