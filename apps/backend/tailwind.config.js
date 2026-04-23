/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/views/**/*.html.erb',
    './app/helpers/**/*.rb',
    './app/assets/stylesheets/**/*.css',
    './app/javascript/**/*.js'
  ],
  safelist: [{ pattern: /form-.+/ }, { pattern: /btn-.+/ }],
  theme: {
    extend: {
      colors: {
        'orange': {
          500: '#E65F00',
          600: '#CC5500',
        },
        'primary': {
          50: '#FFF4E6',
          100: '#FFE8CC',
          200: '#FFD199',
          300: '#FFBA66',
          400: '#FFA333',
          500: '#E65F00',
          600: '#CC5500',
          700: '#B34B00',
          800: '#993F00',
          900: '#803300',
        }
      }
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
