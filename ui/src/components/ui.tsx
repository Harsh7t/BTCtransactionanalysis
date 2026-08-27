/** Shared primitives. Kept deliberately small - a design system for one app is
 *  five components, not a component library. */
import type { ReactNode } from 'react';

export type Layer = 'chain' | 'network' | 'fusion' | 'confirm' | 'danger' | 'neutral';

const LAYER_FG: Record<Layer, string> = {
  chain: 'text-chain', network: 'text-network', fusion: 'text-fusion',
  confirm: 'text-confirm', danger: 'text-danger', neutral: 'text-fg-dim',
};
const LAYER_BG: Record<Layer, string> = {
  chain: 'bg-chain-bg border-chain/40', network: 'bg-network-bg border-network/40',
  fusion: 'bg-fusion-bg border-fusion/40', confirm: 'bg-confirm-bg border-confirm/40',
  danger: 'bg-danger-bg border-danger/40', neutral: 'bg-surface-2 border-border',
};

export function Section({ title, layer = 'fusion', right, children, className = '' }: {
  title: string; layer?: Layer; right?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={className}>
      <div className="flex items-baseline justify-between gap-3 mb-2 pb-1.5 border-b border-border">
        <h2 className={`eyebrow ${LAYER_FG[layer]}`}>{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, className = '', layer = 'neutral' }: {
  children: ReactNode; className?: string; layer?: Layer;
}) {
  return (
    <div className={`border rounded-sm ${LAYER_BG[layer]} ${className}`}>{children}</div>
  );
}

export function Pill({ children, layer = 'neutral', title }: {
  children: ReactNode; layer?: Layer; title?: string;
}) {
  return (
    <span title={title}
      className={`mono text-2xs px-1.5 py-0.5 rounded-sm border whitespace-nowrap ${LAYER_BG[layer]} ${LAYER_FG[layer]}`}>
      {children}
    </span>
  );
}

export function Stat({ label, value, sub, layer = 'neutral' }: {
  label: string; value: ReactNode; sub?: ReactNode; layer?: Layer;
}) {
  return (
    <div className="min-w-0">
      <div className="eyebrow truncate">{label}</div>
      <div className={`mono text-md font-semibold truncate ${LAYER_FG[layer]}`}>{value}</div>
      {sub && <div className="text-2xs text-fg-dim truncate">{sub}</div>}
    </div>
  );
}

/** Confidence bar. The numeric value is always rendered alongside - colour and
 *  length alone must never be the only carrier of meaning. */
export function ConfBar({ value, interval, layer = 'fusion', width = 120 }: {
  value: number; interval?: number; layer?: Layer; width?: number;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const lo = interval ? Math.max(0, value - interval) * 100 : null;
  const hi = interval ? Math.min(1, value + interval) * 100 : null;
  const bar = { chain: 'bg-chain', network: 'bg-network', fusion: 'bg-fusion',
    confirm: 'bg-confirm', danger: 'bg-danger', neutral: 'bg-fg-dim' }[layer];
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 rounded-sm bg-raised overflow-hidden shrink-0"
        style={{ width }}
        role="meter" aria-valuenow={Number(value.toFixed(2))} aria-valuemin={0}
        aria-valuemax={1} aria-label="confidence">
        {lo !== null && hi !== null && (
          <div className="absolute inset-y-0 bg-fg-dim/25"
            style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
        )}
        <div className={`absolute inset-y-0 left-0 ${bar}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="mono text-xs tabular-nums">{value.toFixed(2)}</span>
      {interval !== undefined && (
        <span className="mono text-2xs text-fg-dim tabular-nums">±{interval.toFixed(2)}</span>
      )}
    </div>
  );
}

export function Button({ children, onClick, layer = 'neutral', disabled, title, type = 'button' }: {
  children: ReactNode; onClick?: () => void; layer?: Layer;
  disabled?: boolean; title?: string; type?: 'button' | 'submit';
}) {
  const styles: Record<Layer, string> = {
    chain: 'bg-chain/15 border-chain/50 text-chain hover:bg-chain/25',
    network: 'bg-network/15 border-network/50 text-network hover:bg-network/25',
    fusion: 'bg-fusion/15 border-fusion/50 text-fusion hover:bg-fusion/25',
    confirm: 'bg-confirm/15 border-confirm/50 text-confirm hover:bg-confirm/25',
    danger: 'bg-danger/15 border-danger/50 text-danger hover:bg-danger/25',
    neutral: 'bg-surface-2 border-border-strong text-fg-muted hover:bg-raised hover:text-fg',
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title}
      className={`px-2.5 py-1 text-xs border rounded-sm transition-colors duration-150
        cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed
        min-h-[28px] ${styles[layer]}`}>
      {children}
    </button>
  );
}

export function Empty({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center gap-2">
      {icon && <div className="text-fg-dim">{icon}</div>}
      <div className="text-fg-muted text-md">{title}</div>
      {hint && <div className="text-fg-dim text-sm max-w-md">{hint}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-fg-dim text-sm">
      <span className="inline-block w-2 h-2 rounded-full bg-fusion pulse" />
      {label ?? 'Loading…'}
    </div>
  );
}

/** Inline SVG icons. No emoji - they render inconsistently and read as informal
 *  in a forensics tool. Stroke-based, currentColor, 14px grid. */
export const Icon = {
  arrowLeft: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  ),
  check: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ),
  x: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  ),
  download: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
    </svg>
  ),
  upload: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
    </svg>
  ),
  alert: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01" />
    </svg>
  ),
  offline: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 1l22 22M16.72 11.06A10.94 10.94 0 0119 12.55M5 12.55a10.94 10.94 0 015.17-2.39M10.71 5.05A16 16 0 0122.58 9M1.42 9a15.91 15.91 0 014.7-2.88M8.53 16.11a6 6 0 016.95 0M12 20h.01" />
    </svg>
  ),
};
