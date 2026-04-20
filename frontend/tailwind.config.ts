import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#10213a',
        muted: '#5f7086',
        panel: '#f7fafc',
        line: '#d8e2ee',
        accent: '#17476f',
        accentSoft: '#d9ebfb',
        sand: '#f3efe7',
        success: '#1b6b52',
        warning: '#9a5d1f',
      },
      boxShadow: {
        panel: '0 20px 48px rgba(16, 33, 58, 0.08)',
      },
      borderRadius: {
        xl2: '1.5rem',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
