import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#141413',
        muted: '#5e5d59',
        panel: '#faf9f5',
        line: '#f0eee6',
        accent: '#c96442',
        accentSoft: '#f3e3d7',
        sand: '#e8e6dc',
        success: '#3f7a5b',
        warning: '#9a5d1f',
        parchment: '#f5f4ed',
        ivory: '#faf9f5',
        terracotta: '#c96442',
        coral: '#d97757',
        nearBlack: '#141413',
        warmDark: '#30302e',
        warmDarker: '#1f1f1d',
        charcoal: '#4d4c48',
        olive: '#5e5d59',
        stone: '#87867f',
        warmSilver: '#b0aea5',
        borderCream: '#f0eee6',
        borderWarm: '#e8e6dc',
        ringWarm: '#d1cfc5',
        ringDeep: '#c2c0b6',
        focusBlue: '#3898ec',
        errorWarm: '#b53333',
      },
      boxShadow: {
        panel: '0 1px 0 rgba(20, 20, 19, 0.04), 0 24px 60px -28px rgba(20, 20, 19, 0.16)',
        whisper: '0 4px 24px rgba(0, 0, 0, 0.05)',
        ringWarm: '0 0 0 1px #e8e6dc',
        ringDeep: '0 0 0 1px #c2c0b6',
        ringTerracotta: '0 0 0 1px #c96442',
        ringDark: '0 0 0 1px #30302e',
      },
      borderRadius: {
        xl2: '1.5rem',
      },
      fontFamily: {
        sans: ['"Inter"', '"PingFang SC"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
        serif: ['"Source Serif 4"', '"Spectral"', 'Georgia', '"Songti SC"', 'serif'],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      letterSpacing: {
        tightish: '-0.005em',
      },
    },
  },
  plugins: [],
} satisfies Config;
