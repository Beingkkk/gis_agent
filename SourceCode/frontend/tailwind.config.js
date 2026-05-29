/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'Noto Sans SC',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'SF Mono',
          'Fira Code',
          'Monaco',
          'monospace',
        ],
      },
      borderRadius: {
        'sm': '8px',
        'DEFAULT': '12px',
        'lg': '16px',
      },
      boxShadow: {
        'sm': '0 1px 2px rgba(0,0,0,0.04)',
        'DEFAULT': '0 1px 3px rgba(0,0,0,0.06)',
        'md': '0 4px 12px rgba(0,0,0,0.06)',
        'lg': '0 12px 32px rgba(0,0,0,0.08)',
      },
    },
  },
  plugins: [],
}
