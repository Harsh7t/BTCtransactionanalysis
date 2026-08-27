/** Activity timeline plus the hour-of-day profile.
 *
 *  Two different questions, so two charts rather than one clever one:
 *    WHEN did the money move (bursts betray layering campaigns)
 *    WHAT HOURS does the operator keep (a human in one timezone looks nothing
 *      like an exchange running around the clock)
 *
 *  Hand-drawn SVG rather than a charting library: these are a bar series and a
 *  24-bin histogram, and pulling in a chart framework to draw rectangles would
 *  add weight to an offline bundle for no readability gained.
 */
import { useMemo } from 'react';
import type { Behaviour, TxRow } from '../api';
import { fmt } from '../api';
import { Card, Section } from './ui';

export function Timeline({ behaviour, transactions }: {
  behaviour: Behaviour | null; transactions: TxRow[];
}) {
  const bars = useMemo(() => {
    if (!transactions.length) return [];
    const times = transactions
      .map((t) => new Date(t.ts.replace(' ', 'T') + (t.ts.endsWith('Z') ? '' : 'Z')).getTime())
      .filter((n) => Number.isFinite(n))
      .sort((a, b) => a - b);
    if (!times.length) return [];
    const lo = times[0], hi = times[times.length - 1];
    const span = Math.max(hi - lo, 1);
    // Bucket count follows the data. A fixed 56 buckets against eleven
    // transactions leaves almost every bar empty and the chart reads as blank.
    const N = Math.min(56, Math.max(10, transactions.length * 2));
    const buckets = new Array(N).fill(0);
    const value = new Array(N).fill(0);
    transactions.forEach((t) => {
      const ms = new Date(t.ts.replace(' ', 'T') + (t.ts.endsWith('Z') ? '' : 'Z')).getTime();
      if (!Number.isFinite(ms)) return;
      const b = Math.min(N - 1, Math.floor(((ms - lo) / span) * N));
      buckets[b] += 1;
      value[b] += t.value_out;
    });
    const max = Math.max(...buckets, 1);
    // A burst is a bucket carrying a disproportionate share of the activity -
    // that is the layering window an analyst wants pointed out.
    const mean = buckets.reduce((s, x) => s + x, 0) / N;
    return buckets.map((n, i) => ({
      n, value: value[i], h: n / max, burst: n > Math.max(3, mean * 2.5),
      t: new Date(lo + (span * (i + 0.5)) / N),
    }));
  }, [transactions]);

  const hist = behaviour?.hour_histogram ?? [];
  const hmax = Math.max(...hist, 1);
  const localShift = Math.round((behaviour?.inferred_offset_min ?? 0) / 60);

  return (
    <Section title="Activity" layer="chain" right={
      behaviour && behaviour.diurnality > 0.15 ? (
        <span className="mono text-2xs text-network">
          operating hours ≈ {fmt.offset(behaviour.inferred_offset_min)}
        </span>
      ) : null
    }>
      <Card className="px-3 py-2.5 space-y-3">
        {/* --- when the money moved --- */}
        <div>
          <div className="eyebrow mb-1.5">Transactions over the capture window</div>
          {bars.length === 0 ? (
            <div className="text-fg-dim text-2xs py-4">No transaction times available.</div>
          ) : (
            <>
              <div className="flex items-end gap-px h-16" role="img"
                aria-label="transaction activity over time">
                {bars.map((b, i) => (
                  <div key={i} title={`${b.n} tx · ₿${fmt.btc(b.value)} · ${b.t.toISOString().slice(0, 16).replace('T', ' ')}`}
                    className={`flex-1 min-w-[3px] transition-colors duration-150 rounded-t-[1px]
                      ${b.n === 0 ? 'bg-border' : b.burst ? 'bg-fusion' : 'bg-chain'}
                      hover:bg-fusion`}
                    style={{ height: b.n === 0 ? '2px' : `${Math.max(12, b.h * 100)}%` }} />
                ))}
              </div>
              <div className="flex justify-between mono text-2xs text-fg-dim mt-1">
                <span>{bars[0].t.toISOString().slice(0, 10)}</span>
                {bars.some((b) => b.burst) && (
                  <span className="text-fusion">↑ burst — compressed activity window</span>
                )}
                <span>{bars[bars.length - 1].t.toISOString().slice(0, 10)}</span>
              </div>
            </>
          )}
        </div>

        {/* --- what hours the operator keeps --- */}
        {hist.length === 24 && (
          <div className="pt-2.5 border-t border-border">
            <div className="eyebrow mb-1.5">
              Hour of day
              <span className="text-fg-dim/60 normal-case tracking-normal">
                {' '}— UTC, with inferred local hours beneath
              </span>
            </div>
            <div className="flex items-end gap-px h-12" role="img"
              aria-label="activity by hour of day">
              {hist.map((v, h) => (
                <div key={h} className="flex-1 flex flex-col justify-end"
                  title={`${v} tx at ${String(h).padStart(2, '0')}:00 UTC`}>
                  <div className={`transition-colors duration-150 rounded-t-[1px]
                    ${v === 0 ? 'bg-border' : v / hmax > 0.6 ? 'bg-network' : 'bg-network/55'}`}
                    style={{ height: v === 0 ? '2px' : `${Math.max(14, (v / hmax) * 100)}%` }} />
                </div>
              ))}
            </div>
            <div className="flex mono text-[8px] text-fg-dim mt-0.5">
              {hist.map((_, h) => (
                <span key={h} className="flex-1 text-center">
                  {h % 6 === 0 ? String((h + localShift + 24) % 24).padStart(2, '0') : ''}
                </span>
              ))}
            </div>
            {behaviour && (
              <p className="text-2xs text-fg-dim mt-1.5">
                {behaviour.diurnality > 0.25
                  ? `Concentrated in a narrow band of hours — consistent with a single human
                     operator rather than automated infrastructure. Best-fitting offset
                     ${fmt.offset(behaviour.inferred_offset_min)} (fit ${behaviour.offset_fit.toFixed(2)}).`
                  : `Activity is spread evenly around the clock, so no timezone can be
                     inferred from behaviour. That is itself informative: it points to
                     automation rather than a person.`}
              </p>
            )}
          </div>
        )}
      </Card>
    </Section>
  );
}
