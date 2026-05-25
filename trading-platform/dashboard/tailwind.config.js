/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#090b10',
          secondary: '#0f1219',
          tertiary: '#161a26',
          card: '#131620',
          elevated: '#181c28',
          surface: '#141825',
          border: '#1c2233',
          'border-light': '#262f44',
          hover: '#181c28',
        },
        long: '#22c55e',
        long_muted: 'rgba(34, 197, 94, 0.1)',
        short: '#f43f5e',
        short_muted: 'rgba(244, 63, 94, 0.1)',
        accent: { DEFAULT: '#6366f1', hover: '#818cf8', muted: 'rgba(99, 102, 241, 0.1)' },
        warm: '#f59e0b',
        warm_muted: 'rgba(245, 158, 11, 0.1)',
        up: '#22c55e',
        down: '#f43f5e',
        text: {
          DEFAULT: '#e4e7ef',
          primary: '#f0f1f5',
          secondary: '#8b92a5',
          dim: '#565d73',
          muted: '#3d4356',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        lg: '0.375rem',
        xl: '0.5rem',
      },
    },
  },
  plugins: [],
}
