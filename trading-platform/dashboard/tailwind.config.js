/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Ghost in the Shell cyberpunk palette — Section 9 tactical
        bg: {
          primary: '#0a0a0f',
          secondary: '#0d0d16',
          tertiary: '#111122',
          card: '#0f0f1e',
          elevated: '#14142a',
          surface: '#121224',
          border: '#1a1a3a',
          'border-light': '#25254f',
          hover: '#161630',
        },
        // GitS neon accents — Laughing Man / Section 9 HUD
        neon: {
          cyan: '#00fff7',
          pink: '#ff00ff',
          green: '#c0ff00',
          'cyan-dim': 'rgba(0, 255, 247, 0.4)',
          'pink-dim': 'rgba(255, 0, 255, 0.4)',
          'green-dim': 'rgba(192, 255, 0, 0.4)',
          'cyan-glow': 'rgba(0, 255, 247, 0.08)',
          'pink-glow': 'rgba(255, 0, 255, 0.08)',
          'green-glow': 'rgba(192, 255, 0, 0.08)',
        },
        long: '#00fff7',
        long_muted: 'rgba(0, 255, 247, 0.08)',
        short: '#ff00ff',
        short_muted: 'rgba(255, 0, 255, 0.08)',
        accent: { DEFAULT: '#00fff7', hover: '#66fff9', muted: 'rgba(0, 255, 247, 0.08)' },
        warm: '#c0ff00',
        warm_muted: 'rgba(192, 255, 0, 0.08)',
        up: '#00fff7',
        down: '#ff00ff',
        text: {
          DEFAULT: '#d4d4e8',
          primary: '#e8e8f0',
          secondary: '#7a7a9e',
          dim: '#4a4a6a',
          muted: '#2e2e4a',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        sans: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        gits: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        lg: '0.25rem',
        xl: '0.375rem',
      },
      spacing: {
        'sidebar': '16rem',
        'header': '4rem',
      },
      animation: {
        // Glitch effects
        'glitch-1': 'glitch1 3s infinite',
        'glitch-2': 'glitch2 4s infinite',
        'glitch-skew': 'glitchSkew 5s infinite',
        // CRT / scanline
        'scanline': 'scanline 8s linear infinite',
        'crt-scan': 'crtScan 4s linear infinite',
        'crt-flicker': 'crtFlicker 0.15s ease-in-out 3',
        'crt-vignette': 'crtVignette 10s ease-in-out infinite',
        // Flicker
        'flicker': 'flicker 0.15s ease-in-out 3',
        'flicker-slow': 'flicker 0.25s ease-in-out 6',
        // Neon pulses
        'neon-pulse': 'neonPulse 2s ease-in-out infinite',
        'neon-pulse-pink': 'neonPulsePink 2s ease-in-out infinite',
        'neon-pulse-green': 'neonPulseGreen 2.5s ease-in-out infinite',
        'neon-border-pulse': 'neonBorderPulse 3s ease-in-out infinite',
        // Data streams / rain
        'data-stream': 'dataStream 20s linear infinite',
        'data-stream-2': 'dataStream2 15s linear infinite',
        'data-rain': 'dataRain 3s linear infinite',
        'data-drift': 'dataDrift 60s linear infinite',
        'matrix-rain': 'matrixRain 8s linear infinite',
        // Pulses
        'pulse-cyan': 'pulseCyan 2s ease-in-out infinite',
        'pulse-pink': 'pulsePink 2s ease-in-out infinite',
        'pulse-green': 'pulseGreen 2s ease-in-out infinite',
        'signal-ping': 'signalPing 2s cubic-bezier(0, 0, 0.2, 1) infinite',
        // HUD elements
        'typewriter': 'typewriter 2s steps(40) 1s forwards',
        'cyber-float': 'cyberFloat 3s ease-in-out infinite',
        'grid-scroll': 'gridScroll 30s linear infinite',
        'hud-appear': 'hudAppear 0.6s ease-out forwards',
        'fade-in-up': 'fadeInUp 0.5s ease-out forwards',
        'hud-scan': 'hudScan 4s ease-in-out infinite',
        // Circuit / neural
        'circuit-trace': 'circuitTrace 6s linear infinite',
        'neural-pulse': 'neuralPulse 3s ease-in-out infinite',
        'cyber-spin': 'cyberSpin 0.8s linear infinite',
      },
      keyframes: {
        // ===== GLITCH EFFECTS =====
        glitch1: {
          '0%, 100%': { clipPath: 'inset(0 0 0 0)' },
          '5%': { clipPath: 'inset(20% 0 60% 0)' },
          '10%': { clipPath: 'inset(60% 0 10% 0)' },
          '15%': { clipPath: 'inset(0 0 0 0)' },
        },
        glitch2: {
          '0%, 100%': { clipPath: 'inset(0 0 0 0)', transform: 'translate(0)' },
          '8%': { clipPath: 'inset(40% 0 40% 0)', transform: 'translate(2px, -1px)' },
          '12%': { clipPath: 'inset(10% 0 70% 0)', transform: 'translate(-2px, 1px)' },
          '16%': { clipPath: 'inset(0 0 0 0)', transform: 'translate(0)' },
        },
        glitchSkew: {
          '0%, 100%': { transform: 'skewX(0deg)' },
          '2%': { transform: 'skewX(3deg)' },
          '4%': { transform: 'skewX(-2deg)' },
          '6%': { transform: 'skewX(0deg)' },
          '50%': { transform: 'skewX(0deg)' },
          '52%': { transform: 'skewX(1.5deg)' },
          '54%': { transform: 'skewX(-1deg)' },
          '56%': { transform: 'skewX(0deg)' },
        },
        // ===== CRT EFFECTS =====
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        crtScan: {
          '0%': { top: '-10%' },
          '100%': { top: '110%' },
        },
        crtFlicker: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.85' },
        },
        crtVignette: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.6' },
        },
        flicker: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        // ===== NEON PULSES =====
        neonPulse: {
          '0%, 100%': { boxShadow: '0 0 5px #00fff7, 0 0 10px #00fff7, 0 0 20px rgba(0,255,247,0.3)' },
          '50%': { boxShadow: '0 0 10px #00fff7, 0 0 20px #00fff7, 0 0 40px rgba(0,255,247,0.5)' },
        },
        neonPulsePink: {
          '0%, 100%': { boxShadow: '0 0 5px #ff00ff, 0 0 10px #ff00ff, 0 0 20px rgba(255,0,255,0.3)' },
          '50%': { boxShadow: '0 0 10px #ff00ff, 0 0 20px #ff00ff, 0 0 40px rgba(255,0,255,0.5)' },
        },
        neonPulseGreen: {
          '0%, 100%': { boxShadow: '0 0 5px #c0ff00, 0 0 10px #c0ff00, 0 0 20px rgba(192,255,0,0.3)' },
          '50%': { boxShadow: '0 0 10px #c0ff00, 0 0 20px #c0ff00, 0 0 40px rgba(192,255,0,0.5)' },
        },
        neonBorderPulse: {
          '0%, 100%': { borderColor: 'rgba(0, 255, 247, 0.15)' },
          '50%': { borderColor: 'rgba(0, 255, 247, 0.4)' },
        },
        // ===== DATA STREAMS =====
        dataStream: {
          '0%': { transform: 'translateY(-100%) translateX(0)', opacity: '0' },
          '10%': { opacity: '1' },
          '90%': { opacity: '1' },
          '100%': { transform: 'translateY(100vh) translateX(20px)', opacity: '0' },
        },
        dataStream2: {
          '0%': { transform: 'translateY(100%) translateX(0)', opacity: '0' },
          '10%': { opacity: '0.8' },
          '90%': { opacity: '0.8' },
          '100%': { transform: 'translateY(-100vh) translateX(-15px)', opacity: '0' },
        },
        dataDrift: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        dataRain: {
          '0%': { transform: 'translateY(-100%)', opacity: '0' },
          '10%': { opacity: '0.8' },
          '90%': { opacity: '0.8' },
          '100%': { transform: 'translateY(100%)', opacity: '0' },
        },
        matrixRain: {
          '0%': { transform: 'translateY(-100%) rotate(0deg)', opacity: '0' },
          '5%': { opacity: '0.6' },
          '50%': { opacity: '1' },
          '95%': { opacity: '0.6' },
          '100%': { transform: 'translateY(1000%) rotate(360deg)', opacity: '0' },
        },
        // ===== PULSE EFFECTS =====
        pulseCyan: {
          '0%, 100%': { opacity: '0.6', filter: 'drop-shadow(0 0 2px #00fff7)' },
          '50%': { opacity: '1', filter: 'drop-shadow(0 0 6px #00fff7)' },
        },
        pulsePink: {
          '0%, 100%': { opacity: '0.6', filter: 'drop-shadow(0 0 2px #ff00ff)' },
          '50%': { opacity: '1', filter: 'drop-shadow(0 0 6px #ff00ff)' },
        },
        pulseGreen: {
          '0%, 100%': { opacity: '0.6', filter: 'drop-shadow(0 0 2px #c0ff00)' },
          '50%': { opacity: '1', filter: 'drop-shadow(0 0 6px #c0ff00)' },
        },
        signalPing: {
          '0%': { transform: 'scale(1)', opacity: '1' },
          '75%': { transform: 'scale(2)', opacity: '0' },
          '100%': { transform: 'scale(2)', opacity: '0' },
        },
        // ===== HUD EFFECTS =====
        typewriter: {
          '0%': { width: '0' },
          '100%': { width: '100%' },
        },
        cyberFloat: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' },
        },
        gridScroll: {
          '0%': { transform: 'translate(0, 0)' },
          '100%': { transform: 'translate(-50px, -50px)' },
        },
        hudAppear: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        hudScan: {
          '0%': { transform: 'translateY(-100%)', opacity: '0.3' },
          '25%': { opacity: '0.8' },
          '50%': { transform: 'translateY(100%)', opacity: '0.3' },
          '100%': { transform: 'translateY(-100%)', opacity: '0' },
        },
        // ===== CIRCUIT / NEURAL =====
        circuitTrace: {
          '0%': { strokeDashoffset: '1000' },
          '100%': { strokeDashoffset: '0' },
        },
        neuralPulse: {
          '0%, 100%': { opacity: '0.3', transform: 'scale(1)' },
          '50%': { opacity: '0.8', transform: 'scale(1.1)' },
        },
        cyberSpin: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
      },
    },
  },
  plugins: [],
};