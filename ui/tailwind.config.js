/** Tokens map straight to the CSS custom properties in index.css, so the layer
 *  semantics live in exactly one place and never get re-hardcoded in a component. */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: 'var(--paper)', surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)', 'surface-3': 'var(--surface-3)',
        ink: 'var(--ink)', 'ink-soft': 'var(--ink-soft)', 'ink-dim': 'var(--ink-dim)',
        rule: 'var(--rule)', 'rule-soft': 'var(--rule-soft)',
        chain: 'var(--chain)', network: 'var(--network)', fusion: 'var(--fusion)',
        confirm: 'var(--confirm)', data: 'var(--data)', danger: 'var(--danger)',
        'chain-wash': 'var(--chain-wash)', 'network-wash': 'var(--network-wash)',
        'fusion-wash': 'var(--fusion-wash)', 'confirm-wash': 'var(--confirm-wash)',
        'danger-wash': 'var(--danger-wash)',
      },
      fontFamily: {
        sans: ['IBM Plex Sans', 'system-ui', 'sans-serif'],
        cond: ['IBM Plex Sans Condensed', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['10.5px', '14px'], xs: ['11.5px', '16px'], sm: ['12px', '17px'],
        base: ['13px', '19px'], md: ['14px', '20px'], lg: ['16px', '22px'],
        xl: ['19px', '24px'], '2xl': ['24px', '28px'], '3xl': ['34px', '36px'],
        '4xl': ['44px', '44px'],
      },
      borderRadius: { DEFAULT: '2px', none: '0', sm: '1px', md: '2px' },
      spacing: { '0.5': '2px', '1.5': '6px', '2.5': '10px', '3.5': '14px', '4.5': '18px' },
    },
  },
  plugins: [],
}
