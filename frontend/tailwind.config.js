export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#4F46E5',
        'primary-deep': '#3730A3',
        'primary-soft': '#EEF0FF',
        brand: {
          50: '#EEF0FF',
          100: '#E0E2FF',
          500: '#4F46E5',
          600: '#4338CA',
          700: '#3730A3',
        },
      },
      borderRadius: {
        xl2: '18px',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(15,23,42,.04), 0 1px 3px rgba(15,23,42,.06)',
        card: '0 4px 14px rgba(15,23,42,.06), 0 2px 4px rgba(15,23,42,.04)',
        glow: '0 18px 40px rgba(79,70,229,.12)',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'PingFang SC',
          'Microsoft YaHei',
          'Segoe UI',
          'system-ui',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
}
