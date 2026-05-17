/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: { primary: '#0a0e17', secondary: '#111827', tertiary: '#1e293b', card: '#1a1f2e', border: '#2a3548' },
        accent: { DEFAULT: '#00d4aa', hover: '#00eaba', muted: '#00d4aa20' },
        up: '#00d4aa',
        down: '#f44336',
        text: { primary: '#f1f5f9', secondary: '#94a3b8', muted: '#64748b' },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
