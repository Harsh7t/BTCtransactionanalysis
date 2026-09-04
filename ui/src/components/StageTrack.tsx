/** The nine pipeline stages as a serpentine track.
 *
 * A vertical list of nine rows left most of a wide screen empty and made the
 * pipeline read as a checklist. A boustrophedon path - left to right, turn,
 * right to left, turn, left to right - uses the width it has and reads as what
 * it is: one continuous run of work with the data moving along it.
 *
 * Progress is a second copy of the same path drawn with a dash offset, so the
 * fill follows the curve exactly rather than being faked with segments. One CSS
 * transition on `stroke-dashoffset` animates the whole thing, which is why it
 * stays smooth through the turns.
 *
 * Geometry is computed rather than hand-placed: node centres come from
 * getPointAtLength on the real path, so a node can never drift off the line.
 */
import { useEffect, useRef, useState } from 'react';

const VB_W = 1000, VB_H = 348;
const X0 = 56, X1 = 792, X2 = 208, X3 = 944;
const Y = [62, 172, 282];
const R = (Y[1] - Y[0]) / 2;

const D = `M ${X0} ${Y[0]} H ${X1} A ${R} ${R} 0 0 1 ${X1} ${Y[1]}`
        + ` H ${X2} A ${R} ${R} 0 0 0 ${X2} ${Y[2]} H ${X3}`;

// Straight-run lengths and the two half-circle turns, so node positions can be
// expressed as distances along the path without measuring the DOM first.
const L1 = X1 - X0, ARC = Math.PI * R, L2 = X1 - X2, L3 = X3 - X2;
const TOTAL = L1 + ARC + L2 + ARC + L3;

/** Three nodes per straight run, inset from the ends so none sits on a turn -
 *  a label under a node on the curve collides with the row above it. */
const AT: number[] = [
  ...[0.16, 0.5, 0.84].map((t) => t * L1),
  ...[0.16, 0.5, 0.84].map((t) => L1 + ARC + t * L2),
  ...[0.14, 0.47, 0.8].map((t) => L1 + ARC + L2 + ARC + t * L3),
];

export function StageTrack({ stages, idx, durations }: {
  stages: [string, string][]; idx: number; durations: Record<string, number>;
}) {
  const pathRef = useRef<SVGPathElement>(null);
  const [pts, setPts] = useState<{ x: number; y: number }[]>([]);

  useEffect(() => {
    const p = pathRef.current; if (!p) return;
    setPts(AT.map((len) => { const q = p.getPointAtLength(len); return { x: q.x, y: q.y }; }));
  }, []);

  const filled = idx <= 0 ? AT[0] : Math.min(AT[idx] ?? TOTAL, TOTAL);

  return (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="w-full h-auto" role="img"
         aria-label={`Pipeline progress: stage ${Math.min(idx + 1, stages.length)} of ${stages.length}`}>
      {/* dormant track */}
      <path ref={pathRef} d={D} fill="none" stroke="var(--rule-soft)"
            strokeWidth={14} strokeLinecap="round" />

      {/* the run so far - the same path, revealed by dash offset, so the fill
          follows the curve through both turns instead of stepping between rows */}
      <path d={D} fill="none" stroke="var(--chain)" strokeWidth={14} strokeLinecap="round"
            style={{
              strokeDasharray: TOTAL,
              strokeDashoffset: TOTAL - filled,
              transition: 'stroke-dashoffset 900ms cubic-bezier(.16,1,.3,1)',
            }} />

      {/* Drawn, not a marker: SVG markers scale with stroke-width, and at
          stroke 14 a 7-unit marker renders as a 98px arrowhead. */}
      <path d={`M ${X3 + 2} ${Y[2] - 15} L ${X3 + 30} ${Y[2]} L ${X3 + 2} ${Y[2] + 15} Z`}
            fill="var(--rule-soft)" />

      {pts.map((p, i) => {
        const done = i < idx, live = i === idx;
        const [name] = stages[i] ?? ['', ''];
        const dur = durations[name];
        return (
          <g key={name || i} style={{ transition: 'opacity 300ms' }}>
            {live && (
              <circle cx={p.x} cy={p.y} r={26} fill="var(--chain)" opacity={0.18}>
                <animate attributeName="r" values="21;30;21" dur="1.8s" repeatCount="indefinite" />
                <animate attributeName="opacity" values=".22;.04;.22" dur="1.8s" repeatCount="indefinite" />
              </circle>
            )}
            <circle cx={p.x} cy={p.y} r={19}
                    fill={done || live ? 'var(--chain)' : 'var(--surface)'}
                    stroke={done || live ? 'var(--chain)' : 'var(--rule)'}
                    strokeWidth={3}
                    style={{ transition: 'fill 500ms ease, stroke 500ms ease' }} />
            {done ? (
              <path d={`M ${p.x - 6} ${p.y} l 4.4 4.6 L ${p.x + 7} ${p.y - 5.4}`}
                    fill="none" stroke="var(--surface)" strokeWidth={3}
                    strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <text x={p.x} y={p.y + 5} textAnchor="middle" fontSize={15} fontWeight={700}
                    fill={live ? 'var(--surface)' : 'var(--ink-dim)'}
                    style={{ fontFamily: 'Archivo, sans-serif' }}>
                {i + 1}
              </text>
            )}

            <text x={p.x} y={p.y + 40} textAnchor="middle" fontSize={15}
                  fontWeight={done || live ? 700 : 500}
                  fill={done || live ? 'var(--ink)' : 'var(--ink-dim)'}
                  style={{ fontFamily: 'Archivo, sans-serif', textTransform: 'uppercase',
                           letterSpacing: '.01em', transition: 'fill 400ms' }}>
              {name}
            </text>
            {dur != null && (
              <text x={p.x} y={p.y + 56} textAnchor="middle" fontSize={12}
                    fill="var(--confirm)"
                    style={{ fontFamily: '"Spline Sans Mono", monospace' }}>
                {dur.toFixed(2)}s
              </text>
            )}
            {live && dur == null && (
              <text x={p.x} y={p.y + 56} textAnchor="middle" fontSize={12}
                    fill="var(--chain)"
                    style={{ fontFamily: '"Spline Sans Mono", monospace' }}>
                running
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
