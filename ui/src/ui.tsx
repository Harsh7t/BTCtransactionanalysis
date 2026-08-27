/** Shared primitives.
 *
 * Every one of these is deliberately flat: hairline border, square corner, no
 * shadow. Panels sit ON the paper, they do not float above it. That restraint is
 * what makes a tool read as an instrument rather than as a web page.
 */
import type { ReactNode, CSSProperties } from 'react';

export type Layer = 'chain' | 'network' | 'fusion' | 'confirm' | 'data' | 'danger';

const LAYER_VAR: Record<Layer, string> = {
  chain: 'var(--chain)', network: 'var(--network)', fusion: 'var(--fusion)',
  confirm: 'var(--confirm)', data: 'var(--data)', danger: 'var(--danger)',
};
const LAYER_WASH: Record<Layer, string> = {
  chain: 'var(--chain-wash)', network: 'var(--network-wash)', fusion: 'var(--fusion-wash)',
  confirm: 'var(--confirm-wash)', data: 'var(--surface-2)', danger: 'var(--danger-wash)',
};

export const layerColor = (l: Layer) => LAYER_VAR[l];
export const layerWash = (l: Layer) => LAYER_WASH[l];

/** Section label. Mono, letterspaced, tinted by the data layer it introduces. */
export function Eyebrow({ children, layer, right }:
  { children: ReactNode; layer?: Layer; right?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 mb-2">
      <span className="eyebrow" style={layer ? { color: LAYER_VAR[layer] } : undefined}>
        {children}
      </span>
      {right ? <span className="eyebrow">{right}</span> : null}
    </div>
  );
}

/** A bordered region. `accent` draws the plate's 4px left rule. */
export function Panel({ children, accent, className = '', pad = true, style }: {
  children: ReactNode; accent?: Layer; className?: string; pad?: boolean;
  style?: CSSProperties;
}) {
  return (
    <section
      className={`bg-surface border border-rule ${pad ? 'p-3.5' : ''} ${className}`}
      style={{ ...(accent ? { borderLeft: `4px solid ${LAYER_VAR[accent]}` } : {}), ...style }}
    >
      {children}
    </section>
  );
}

/** Inline metric: label above, figure below. Used across the receipt strip. */
export function Stat({ label, value, sub, layer, mono = true }: {
  label: string; value: ReactNode; sub?: ReactNode; layer?: Layer; mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="eyebrow truncate">{label}</div>
      <div
        className={`${mono ? 'mono' : 'font-cond'} text-md font-semibold leading-tight truncate`}
        style={layer ? { color: LAYER_VAR[layer] } : undefined}
      >
        {value}
      </div>
      {sub ? <div className="text-2xs text-ink-dim truncate mono">{sub}</div> : null}
    </div>
  );
}

/** Horizontal magnitude bar. The one place a filled rectangle means a number. */
export function Bar({ value, max = 1, layer = 'fusion', width = 150, height = 8, negative }: {
  value: number; max?: number; layer?: Layer; width?: number | '100%'; height?: number;
  negative?: boolean;
}) {
  const pct = Math.max(0, Math.min(1, Math.abs(value) / (max || 1)));
  return (
    <span
      className="inline-block align-middle bg-surface-3 border border-rule-soft"
      style={{ width, height }}
      role="img"
      aria-label={`${value.toFixed(3)} of ${max}`}
    >
      <span
        className="block h-full"
        style={{ width: `${pct * 100}%`, background: negative ? 'var(--data)' : LAYER_VAR[layer] }}
      />
    </span>
  );
}

/** Small square-cornered tag. Never used decoratively — always carries a fact. */
export function Tag({ children, layer = 'data', title }:
  { children: ReactNode; layer?: Layer; title?: string }) {
  return (
    <span
      title={title}
      className="mono text-2xs px-1.5 py-0.5 border whitespace-nowrap"
      style={{ color: LAYER_VAR[layer], borderColor: LAYER_VAR[layer], background: LAYER_WASH[layer] }}
    >
      {children}
    </span>
  );
}

export function Button({ children, onClick, variant = 'default', disabled, title, type }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; title?: string;
  variant?: 'default' | 'primary' | 'ghost' | 'danger'; type?: 'button' | 'submit';
}) {
  const base =
    'mono text-xs px-2.5 h-8 inline-flex items-center gap-1.5 border transition-colors ' +
    'duration-150 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer select-none';
  const v = {
    default: 'bg-surface border-ink text-ink hover:bg-surface-3',
    primary: 'text-white border-transparent hover:opacity-90',
    ghost: 'bg-transparent border-rule text-ink-soft hover:bg-surface-3 hover:text-ink',
    danger: 'bg-surface border-danger text-danger hover:bg-danger-wash',
  }[variant];
  return (
    <button
      type={type || 'button'} onClick={onClick} disabled={disabled} title={title}
      className={`${base} ${v}`}
      style={variant === 'primary' ? { background: 'var(--confirm)' } : undefined}
    >
      {children}
    </button>
  );
}

/** Filter chip. Pressed state is a real aria-pressed toggle, not a colour trick. */
export function Chip({ active, onClick, children, layer = 'fusion' }: {
  active?: boolean; onClick?: () => void; children: ReactNode; layer?: Layer;
}) {
  return (
    <button
      onClick={onClick} aria-pressed={!!active}
      className="mono text-xs px-2.5 h-7 border transition-colors duration-150 cursor-pointer whitespace-nowrap"
      style={active
        ? { color: LAYER_VAR[layer], borderColor: LAYER_VAR[layer], background: LAYER_WASH[layer] }
        : { color: 'var(--ink-soft)', borderColor: 'var(--rule)', background: 'var(--surface)' }}
    >
      {children}
    </button>
  );
}

/** Empty / loading / error state. Always says what to do next. */
export function Notice({ title, children, layer = 'data' }:
  { title: string; children?: ReactNode; layer?: Layer }) {
  return (
    <div className="border border-rule bg-surface-2 p-4" style={{ borderLeft: `4px solid ${LAYER_VAR[layer]}` }}>
      <div className="font-cond font-semibold uppercase text-md tracking-tight">{title}</div>
      {children ? <div className="text-sm text-ink-soft mt-1 max-w-[70ch]">{children}</div> : null}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-soft mono">
      <span className="inline-block w-2 h-2 bg-fusion blink" />
      {label}
    </div>
  );
}

/* --- Icons. Inline SVG, stroke-only, sized to the type. Never emoji. --------- */
type IcoProps = { className?: string };
const ico = (d: ReactNode) => ({ className = 'w-3.5 h-3.5' }: IcoProps) => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"
       strokeLinecap="square" className={className} aria-hidden="true">{d}</svg>
);

export const IconBack = ico(<path d="M10 3 5 8l5 5" />);
export const IconCheck = ico(<path d="M3 8.5 6.5 12 13 4" />);
export const IconX = ico(<><path d="M4 4l8 8" /><path d="M12 4l-8 8" /></>);
export const IconExport = ico(<><path d="M8 11V2" /><path d="M5 5l3-3 3 3" /><path d="M2.5 10v4h11v-4" /></>);
export const IconUpload = ico(<><path d="M8 2v9" /><path d="M5 5l3-3 3 3" /><path d="M2.5 13h11" /></>);
export const IconFilter = ico(<path d="M2 3h12l-4.5 5.5V14L6.5 12V8.5z" />);
export const IconGraph = ico(<><circle cx="4" cy="12" r="1.8" /><circle cx="12" cy="4" r="1.8" /><circle cx="12" cy="12" r="1.8" /><path d="M5.4 10.8 10.6 5.4M6 12h4" /></>);
