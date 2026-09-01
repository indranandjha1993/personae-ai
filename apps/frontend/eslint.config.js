import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'coverage'] },
  {
    // Worklets run in AudioWorkletGlobalScope, not the window scope, so the
    // browser globals list does not cover their APIs.
    files: ['public/**/*.worklet.js'],
    languageOptions: {
      globals: { ...globals.worker, AudioWorkletProcessor: 'readonly', registerProcessor: 'readonly', sampleRate: 'readonly', currentTime: 'readonly' },
    },
  },
  js.configs.recommended,
  {
    // Type-aware rules are scoped to TypeScript sources: the flat config and
    // any other plain JS are not part of the TS project, and applying typed
    // rules to them makes ESLint fail outright.
    files: ['**/*.{ts,tsx}'],
    extends: [...tseslint.configs.strictTypeChecked],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: {
      // The documented configs['recommended-latest'] path crashes ESLint 10;
      // the flat namespace is the working one.
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.flat['recommended-latest'].rules,
      'react-refresh/only-export-components': 'warn',
    },
  },
)
