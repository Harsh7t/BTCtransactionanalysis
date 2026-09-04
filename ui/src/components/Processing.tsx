/** The nine stages, while they run.
 *
 * A 13-second wait on demo data and 105 seconds on bulk is too long for the
 * hairline progress bar this used to be. It is also the most persuasive thing
 * the product does in a live demo: watching it consume half a million records
 * lands harder than being told it can.
 *
 * The stage names are the pipeline's own, and the timings are real - the API
 * reports which stage is executing, so nothing here is a fake progress bar.
 */
import { useEffect, useState } from 'react';
import type { Job } from '../api';
import { Propagation } from './Propagation';

const STAGES: [string, string][] = [
  ['ingest', 'parse CSV / JSONL / XML, quarantine bad rows'],
  ['enrich', 'resolve every IP to ASN and country, offline'],
  ['resolve', 'collapse addresses into actors — common-input ownership'],
  ['graph', 'actor-to-actor money flow, entity × IP matrix'],
  ['features', '132 features per actor, including Node2Vec'],
  ['detect', 'score every actor, calibrate the probability'],
  ['attribute', 'which IP is really theirs — with FDR control'],
  ['explain', 'exact SHAP, turned into English'],
  ['store', 'write the case files'],
];

export function Processing({ job }: { job: Job }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t0 = performance.now();
    const id = setInterval(() => setElapsed((performance.now() - t0) / 1000), 100);
    return () => clearInterval(id);
  }, [job.job_id]);

  const idx = Math.max(0, STAGES.findIndex(([s]) => s === (job.stage || 'ingest')));

  return (
    <div className="relative flex-1 min-h-0 overflow-hidden flex flex-col">
      {/* The same field as the landing screen, still running. It is not filler:
          the pipeline is at this moment resolving exactly this - announcements
          spread across peers - into actors and attributions, and the field
          keeps the reason for the wait on screen while it happens. */}
      <Propagation className="absolute inset-0 w-full h-full" />

      {/* Radial rather than the landing's horizontal veil, because this layout
          is centred: the ground is quiet under the stage list and opens out to
          the field at the edges. */}
      <div aria-hidden className="absolute inset-0 pointer-events-none"
           style={{ background:
             'radial-gradient(ellipse 46% 52% at 50% 46%, var(--paper) 0%,' +
             ' color-mix(in srgb, var(--paper) 60%, transparent) 42%,' +
             ' color-mix(in srgb, var(--paper) 10%, transparent) 72%, transparent 90%)' }} />

      <div className="relative flex-1 min-h-0 overflow-y-auto">
        <div className="min-h-full flex items-center justify-center p-6">
      <div className="w-full max-w-3xl">
        <div className="flex items-baseline gap-3 mb-1">
          <h1 className="display text-ink">scoring</h1>
          <span className="mono text-md text-ink-soft">{job.file}</span>
        </div>
        <p className="text-sm text-ink-soft mb-6">
          Nine stages, on this machine, with no network. Elapsed{' '}
          <span className="mono text-ink font-semibold">{elapsed.toFixed(1)}s</span>.
        </p>

        <ol className="border border-rule bg-surface">
          {STAGES.map(([name, what], i) => {
            const done = i < idx, live = i === idx;
            return (
              <li key={name}
                  className={`flex items-center gap-3 px-3.5 py-2 border-b border-rule-soft
                              last:border-0 ${live ? 'bg-chain-wash' : ''}`}>
                <span aria-hidden
                      className={`w-2 h-2 shrink-0 ${live ? 'blink' : ''}`}
                      style={{ background: done ? 'var(--confirm)'
                        : live ? 'var(--chain)' : 'var(--rule)' }} />
                <span className={`font-cond font-bold uppercase tracking-tight text-sm w-24 shrink-0
                                  ${done || live ? 'text-ink' : 'text-ink-dim'}`}>
                  {name}
                </span>
                <span className={`text-2xs ${live ? 'text-ink-soft' : 'text-ink-dim'}`}>
                  {what}
                </span>
                {done && <span className="ml-auto text-2xs text-confirm shrink-0">done</span>}
              </li>
            );
          })}
        </ol>

        <div className="mt-3 h-0.5 bg-surface-3 overflow-hidden">
          <div className="h-full bg-chain transition-all duration-300"
               style={{ width: `${((idx + 1) / STAGES.length) * 100}%` }} />
        </div>
      </div>
        </div>
      </div>
    </div>
  );
}
