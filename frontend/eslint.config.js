import reactHooks from 'eslint-plugin-react-hooks'
export default [{ files: ['src/**/*.{js,jsx}'], plugins: { 'react-hooks': reactHooks },
  languageOptions: { ecmaVersion: 2023, sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } },
    globals: { window: 'readonly', document: 'readonly', localStorage: 'readonly', URL: 'readonly', Blob: 'readonly', console: 'readonly' } },
  rules: { ...reactHooks.configs.recommended.rules } }]
