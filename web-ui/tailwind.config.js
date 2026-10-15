/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    screens: {
      'xs': '475px',
      'sm': '640px',
      'md': '768px',
      'lg': '1024px',
      'xl': '1280px',
      '2xl': '1536px',
    },
    extend: {
      fontFamily: {
        plus: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive) / <alpha-value>)",
          foreground: "hsl(var(--destructive-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Aplot AI Design Tokens
        'bg-primary': {
          DEFAULT: '#0a0a0a',
          light: '#eef1f6',
        },
        'bg-sidebar': {
          DEFAULT: '#0f0f0f',
          light: '#e4e9f1',
        },
        'bg-surface': {
          DEFAULT: '#161616',
          light: '#ffffff',
        },
        'bg-input': {
          DEFAULT: '#111111',
          light: '#f5f7fa',
        },
        'bg-button': {
          DEFAULT: '#1a1a1a',
          light: '#e8ecf2',
        },
        'bg-pill': {
          DEFAULT: '#1c1c1e',
          light: '#ffffff',
        },
        'bg-pill-hover': {
          DEFAULT: '#262628',
          light: '#eef1f6',
        },
        'bg-icon-hover': {
          DEFAULT: '#1a1a1a',
          light: '#d8dee8',
        },
        'border-subtle': {
          DEFAULT: '#2a2a2e',
          light: '#d4d8e0',
        },
        'border-input': {
          DEFAULT: '#2c2c30',
          light: '#d8dce4',
        },
        'text-primary': {
          DEFAULT: '#f5f5f7',
          light: '#1d1d1f',
        },
        'text-secondary': {
          DEFAULT: '#a1a1aa',
          light: '#6e6e73',
        },
        'text-tertiary': {
          DEFAULT: '#6e6e73',
          light: '#86868b',
        },
        'accent-blue': {
          DEFAULT: '#0071e3',
          light: '#0071e3',
        },
        'accent-blue-hover': {
          DEFAULT: '#0077ed',
          light: '#0077ed',
        },
        'accent-blue-light': {
          DEFAULT: '#5ac8fa',
          light: '#5ac8fa',
        },
        'mascot-blue': {
          DEFAULT: '#5b9dff',
          light: '#5b9dff',
        },
        'success': {
          DEFAULT: '#34c759',
          light: '#34c759',
        },
        'warning': {
          DEFAULT: '#ff9500',
          light: '#ff9500',
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xs: "calc(var(--radius) - 6px)",
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        'sm': '0 1px 2px rgba(0,0,0,0.3)',
        'sm-light': '0 1px 2px rgba(0,0,0,0.05)',
        'md': '0 4px 12px rgba(0,0,0,0.4)',
        'md-light': '0 4px 12px rgba(0,0,0,0.08)',
        'lg': '0 8px 24px rgba(0,0,0,0.5)',
        'lg-light': '0 8px 24px rgba(0,0,0,0.12)',
        'glow-blue': '0 0 20px rgba(0,113,227,0.3)',
        'glow-blue-light': '0 0 20px rgba(0,113,227,0.15)',
        'input-focus': '0 0 0 2px rgba(0,113,227,0.3)',
        'input-focus-light': '0 0 0 2px rgba(0,113,227,0.2)',
      },
      transitionTimingFunction: {
        'spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "caret-blink": {
          "0%,70%,100%": { opacity: "1" },
          "20%,50%": { opacity: "0" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(1)", opacity: "0.4" },
          "100%": { transform: "scale(1.8)", opacity: "0" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(30px) scale(0.95)" },
          "100%": { opacity: "1", transform: "translateX(0) scale(1)" },
        },
        "slide-in-left": {
          "0%": { opacity: "0", transform: "translateX(-20px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "shimmer": {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "typing-dot": {
          "0%, 80%, 100%": { transform: "scale(1)" },
          "40%": { transform: "scale(1.4)" },
        },
        "float": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-4px)" },
        },
        "blink": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        "connection-pulse": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.3)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "caret-blink": "caret-blink 1.25s ease-out infinite",
        "pulse-ring": "pulse-ring 1.5s ease-out infinite",
        "fade-in-up": "fade-in-up 0.6s ease-out forwards",
        "slide-in-right": "slide-in-right 0.3s ease-out forwards",
        "slide-in-left": "slide-in-left 0.3s ease-out forwards",
        "shimmer": "shimmer 2s linear infinite",
        "typing-dot": "typing-dot 1.2s ease-in-out infinite",
        "float": "float 3s ease-in-out infinite",
        "blink": "blink 1s step-end infinite",
        "connection-pulse": "connection-pulse 1s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
