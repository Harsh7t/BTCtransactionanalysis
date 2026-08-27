/** Attribution accuracy vs observation coverage — the honest-engineering chart.
 *
 *  Plotted rather than tabulated because the SHAPE is the argument: accuracy
 *  falls away as the collector sees less of the network, and a single number
 *  quoted at an unstated coverage would hide exactly that.
 *
 *  The random-choice baseline is drawn too, and it is the more interesting line.
 *  At very low coverage it CROSSES ABOVE the measured accuracy: with almost no
 *  observations there are few candidates, so guessing is easy, while the engine
 *  is mostly seeing relays rather than origins and confidently picks wrong.
 *  That crossing point is a real limit of the method and is left visible.
 */
type Row = {
  coverage: number; top1_accuracy: number; top3_accuracy: number;
  mrr: number; random_choice_baseline: number;
};

export function SensitivityCurve({ rows }: { rows: Row[] }) {
  if (!rows?.length) return null;
  const W = 440, H = 230, P = 36;
  const sx = (v: number) => P + v * (W - P - 12);
  const sy = (v: number) => H - P - v * (H - P - 16);
  const line = (k: keyof Row) =>
    rows.map((r) => `${sx(r.coverage)},${sy(Number(r[k]))}`).join(' ');

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
           aria-label="Attribution accuracy against observation coverage">
        {[0.25, 0.5, 0.75, 1].map((g) => (
          <line key={g} x1={P} y1={sy(g)} x2={W - 12} y2={sy(g)}
                stroke="var(--rule-soft)" strokeWidth={1} />
        ))}
        <polyline fill="none" stroke="var(--data)" strokeWidth={1.4}
                  strokeDasharray="3 3" points={line('random_choice_baseline')} />
        <polyline fill="none" stroke="var(--chain)" strokeWidth={1.6}
                  strokeDasharray="5 3" points={line('top3_accuracy')} />
        <polyline fill="none" stroke="var(--network)" strokeWidth={2.4}
                  points={line('top1_accuracy')} />
        {rows.map((r, i) => (
          <circle key={i} cx={sx(r.coverage)} cy={sy(r.top1_accuracy)} r={3}
                  fill="var(--network)">
            <title>{`coverage ${(r.coverage * 100).toFixed(0)}% → top-1 ${r.top1_accuracy.toFixed(3)} (chance ${r.random_choice_baseline.toFixed(3)})`}</title>
          </circle>
        ))}
        <line x1={P} y1={H - P} x2={W - 12} y2={H - P} stroke="var(--ink-soft)" strokeWidth={1} />
        <line x1={P} y1={16} x2={P} y2={H - P} stroke="var(--ink-soft)" strokeWidth={1} />
        <text x={8} y={sy(1) + 3} fontSize="9" fill="var(--ink-dim)" fontFamily="IBM Plex Mono">1.0</text>
        <text x={8} y={sy(0) + 3} fontSize="9" fill="var(--ink-dim)" fontFamily="IBM Plex Mono">0.0</text>
        <text x={P} y={H - 12} fontSize="9" fill="var(--ink-dim)" fontFamily="IBM Plex Mono">0%</text>
        <text x={W - 40} y={H - 12} fontSize="9" fill="var(--ink-dim)" fontFamily="IBM Plex Mono">100%</text>
        <text x={P + 62} y={H - 12} fontSize="9" fill="var(--ink-dim)" fontFamily="IBM Plex Mono">
          announcements observed →
        </text>
      </svg>
      <div className="mono text-2xs text-ink-dim flex flex-wrap gap-x-3">
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1"
                    style={{ background: 'var(--network)' }} />top-1</span>
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1"
                    style={{ background: 'var(--chain)' }} />top-3</span>
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1"
                    style={{ background: 'var(--data)' }} />random choice</span>
      </div>
    </div>
  );
}
