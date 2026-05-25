/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Surfaces
        bg: {
          primary: '#0a0e17',
          secondary: '#111827',
          tertiary: '#1e293b',
          card: '#151b2b',
          elevated: '#1c2337',
          surface: '#1a2035',
          border: '#1e2a3a',
          border_light: '#2a3548',
          hover: '#1e2740',
        },
        // Long (buy/green)
        long: '#10b981',
        long_muted: 'rgba(16, 185, 129, 0.12)',
        // Short (sell/red)
        short: '#ef4444',
        short_muted: 'rgba(239, 68, 68, 0.12)',
        // Accent (teal/brand)
        accent: { DEFAULT: '#06b6d4', hover: '#22d3ee', muted: 'rgba(6, 182, 212, 0.12)' },
        // Warm (amber/amber accent for Solana, stop orders)
        warm: '#f59e0b',
        warm_muted: 'rgba(245, 158, 11, 0.12)',
        // Up/down (legacy aliases)
        up: '#10b981',
        down: '#ef4444',
        // Text
        text: {
          DEFAULT: '#e2e8f0',
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          dim: '#64748b',
          muted: '#4b5563',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        lg: '0.5rem',
        xl: '0.625rem',
      },
    },
  },
  plugins: [],
}
