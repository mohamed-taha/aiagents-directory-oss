module.exports = {
  content: [
    './aiagents_directory/templates/**/*.html',
    './aiagents_directory/static/**/*.js',
    './node_modules/flowbite/**/*.js'
  ],
  safelist: [
    'w-64',
    'w-1/2',
    'rounded-l-lg',
    'rounded-r-lg',
    'bg-gray-200',
    'grid-cols-4',
    'grid-cols-7',
    'h-6',
    'leading-6',
    'h-9',
    'leading-9',
    'shadow-lg',
    'bg-opacity-50',
    'dark:bg-opacity-80'
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#121826',
          800: '#1E293B',
          700: '#334155',
          600: '#475569',
          100: '#F1F5F9',
        },
        accent: {
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
        },
        gray: {
          50: '#F8FAFC',  // Very light background
          100: '#F1F5F9', // Borders and dividers
          200: '#E2E8F0', // Subtle backgrounds
          300: '#CBD5E1', // Disabled states
          400: '#94A3B8', // Placeholder text
          500: '#64748B', // Secondary text
          600: '#475569', // Primary text
          700: '#334155', // Headings
          800: '#1E293B', // Heavy text
          900: '#0F172A', // Extra heavy text
        }
      }
    }
  },

  plugins: [
    require('@tailwindcss/typography'),
    require('flowbite/plugin')
  ],
}