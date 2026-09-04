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
import { useEffect, useRef, useState } from 'react';
import type { Job } from '../api';
import { Propagation } from './Propagation';
import { Sonar } from './Sonar';

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

  // The API reports which stage is running and nothing else - no row counts
  // until the receipt arrives - so the per-stage durations are timed here, on
  // the transition. They are real measurements of real work; inventing a
  // throughput number to fill the panel would be worse than an empty one.
  const [durations, setDurations] = useState<Record<string, number>>({});
  const markRef = useRef({ stage: -1, at: 0 });
  useEffect(() => {
    const now = performance.now();
    const m = markRef.current;
    if (m.stage === -1) { markRef.current = { stage: idx, at: now }; return; }
    if (idx !== m.stage) {
      const name = STAGES[m.stage]?.[0];
      if (name) setDurations((d) => ({ ...d, [name]: (now - m.at) / 1000 }));
      markRef.current = { stage: idx, at: now };
    }
  }, [idx]);

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
        <div className="flex items-start gap-6 mb-7">
          <div className="min-w-0">
            <div className="flex items-baseline gap-3 flex-wrap">
              <h1 className="display text-ink">scoring</h1>
              <span className="mono text-md text-ink-soft break-all">{job.file}</span>
            </div>
            <p className="text-sm text-ink-soft mt-1.5">
              Nine stages, on this machine, with no network.
            </p>
            <div className="flex items-baseline gap-5 mt-3 flex-wrap">
              <span>
                <span className="figure text-ink" style={{ fontSize: 30 }}>
                  {elapsed.toFixed(1)}
                </span>
                <span className="mono text-sm text-ink-soft">s</span>
                <span className="colhead block mt-0.5">elapsed</span>
              </span>
              <span>
                <span className="figure text-chain" style={{ fontSize: 30 }}>
                  {Math.min(idx + 1, STAGES.length)}
                </span>
                <span className="mono text-sm text-ink-soft">/{STAGES.length}</span>
                <span className="colhead block mt-0.5">stage</span>
              </span>
            </div>
          </div>
          <div className="ml-auto shrink-0 hidden sm:block">
            <Sonar stage={idx} />
          </div>
        </div>

        <ol className="relative">
          {STAGES.map(([name, what], i) => {
            const done = i < idx, live = i === idx;
            const isLast = i === STAGES.length - 1;
            return (
              <li key={name} className="relative flex gap-3.5 pl-0.5">
                {/* The rail. Two stacked segments: a dormant track and a chain
                    fill whose height transitions, so progress GROWS down the
                    page instead of snapping between rows. */}
                {!isLast && (
                  <span aria-hidden className="absolute left-[9px] top-5 w-0.5 h-[calc(100%-4px)]
                                               bg-rule-soft overflow-hidden">
                    <span className="block w-full bg-chain transition-[height] duration-700 ease-out"
                          style={{ height: done ? '100%' : live ? '45%' : '0%' }} />
                  </span>
                )}

                <span aria-hidden
                      className={`relative z-10 mt-1 w-[19px] h-[19px] shrink-0 rounded-full border-2
                                  flex items-center justify-center transition-all duration-500
                                  ${done ? 'border-chain bg-chain'
                                    : live ? 'border-chain bg-surface'
                                           : 'border-rule bg-surface'}`}>
                  {done ? (
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none"
                         stroke="var(--surface)" strokeWidth="2"
                         strokeLinecap="round" strokeLinejoin="round">
                      <path d="M2 5.2 L4.1 7.3 L8 3.2" />
                    </svg>
                  ) : live ? (
                    <span className="w-[7px] h-[7px] rounded-full bg-chain animate-ping-soft" />
                  ) : null}
                </span>

                <div className={`flex-1 min-w-0 pb-5 ${isLast ? 'pb-0' : ''}`}>
                  <div className="flex items-baseline gap-2.5 flex-wrap">
                    <span className={`font-cond font-bold uppercase tracking-tight text-sm
                                      transition-colors duration-300
                                      ${done || live ? 'text-ink' : 'text-ink-dim'}`}>
                      {name}
                    </span>
                    {durations[name] != null && (
                      <span className="mono text-2xs text-confirm">
                        {durations[name].toFixed(2)}s
                      </span>
                    )}
                    {live && (
                      <span className="mono text-2xs text-chain">running</span>
                    )}
                  </div>
                  <div className={`text-2xs mt-0.5 transition-colors duration-300
                                   ${live ? 'text-ink-soft' : 'text-ink-dim'}`}>
                    {what}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>

      </div>
        </div>
      </div>
    </div>
  );
}
