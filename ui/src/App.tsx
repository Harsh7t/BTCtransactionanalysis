/** Application shell.
 *
 * Dark chrome, dense light body — the arrangement Plates 04-06 specify. Routing
 * is the URL hash: four screens and a case-file deep link do not justify a
 * router dependency, and a real hash means an analyst can bookmark a case and
 * the browser back button behaves.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ThemeToggle } from './ThemeToggle';
import { api, fmt, type Job, type Run } from './api';
import { Button, IconUpload, Notice, Spinner } from './ui';
import { AlertQueue } from './components/AlertQueue';
import { CaseFile } from './components/CaseFile';
import { ModelPanel } from './components/ModelPanel';
import { Provenance } from './components/Provenance';

type View = { tab: 'alerts' | 'model' | 'provenance'; entity?: string };

function parseHash(): View {
  const h = window.location.hash.replace(/^#\/?/, '');
  const [tab, entity] = h.split('/');
  if (tab === 'case' && entity) return { tab: 'alerts', entity: decodeURIComponent(entity) };
  if (tab === 'model' || tab === 'provenance') return { tab };
  return { tab: 'alerts' };
}

const STAGES = ['ingest', 'enrich', 'resolve', 'graph', 'features',
                'detect', 'attribute', 'explain', 'store'];

export default function App() {
  const [view, setView] = useState<View>(parseHash);
  const [run, setRun] = useState<Run | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [health, setHealth] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onHash = () => setView(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const refresh = useCallback(() => {
    api.latestRun().then((r) => setRun(r.run)).catch(() => {});
  }, []);
  useEffect(() => { refresh(); api.health().then(setHealth).catch(() => {}); }, [refresh]);

  // Poll while a run is executing. This is the throughput counter the demo hangs on.
  useEffect(() => {
    if (!job || job.state !== 'running') return;
    const id = setInterval(() => {
      api.job(job.job_id).then((j) => {
        setJob(j);
        if (j.state === 'done') { refresh(); window.location.hash = '#/alerts'; }
      }).catch(() => {});
    }, 400);
    return () => clearInterval(id);
  }, [job, refresh]);

  const go = (tab: View['tab'], entity?: string) => {
    window.location.hash = entity ? `#/case/${encodeURIComponent(entity)}` : `#/${tab}`;
  };

  async function onFile(f: File | undefined) {
    if (!f) return;
    const { job_id } = await api.upload(f);
    setJob({ job_id, state: 'running', stage: 'ingest', file: f.name });
  }

  async function runSample() {
    const { job_id } = await api.startRun();
    setJob({ job_id, state: 'running', stage: 'ingest', file: 'bundled sample' });
  }

  const running = job?.state === 'running';
  const stageIdx = running ? Math.max(0, STAGES.indexOf(job?.stage || 'ingest')) : -1;

  return (
    <div className="min-h-full flex flex-col">
      {/* ---------------- chrome ---------------- */}
      {/* `min-w-0` on the flex children and a shrinking wordmark: without them the
          three groups summed to 489px inside a 375px viewport, pushing the OFFLINE
          pill to clip mid-word and taking `load capture` - the only data-ingest
          control in the app - entirely off-screen on a phone. */}
      <header className="bg-chrome text-white flex items-center gap-2 sm:gap-4 px-2.5 sm:px-3.5 h-12 shrink-0">
        <div className="flex items-baseline gap-2 shrink-0">
          <span className="font-cond font-extrabold uppercase text-lg tracking-tighter">BTC-Fusion</span>
          <span className="mono text-2xs text-white/45 hidden md:inline">
            network ⇄ chain attribution
          </span>
        </div>

        <nav className="flex items-center gap-0.5 ml-1 sm:ml-3 min-w-0" aria-label="Main">
          {([['alerts', 'Alerts'], ['model', 'Model'], ['provenance', 'Provenance']] as const)
            .map(([t, label]) => {
              const active = view.tab === t && !(t === 'alerts' && view.entity);
              return (
                <button key={t} onClick={() => go(t)}
                        aria-current={active ? 'page' : undefined}
                        className="text-xs px-2 sm:px-3 h-12 border-b-2 transition-colors duration-150 cursor-pointer"
                        style={active
                          ? { borderColor: '#fff', color: '#fff' }
                          : { borderColor: 'transparent', color: 'rgba(255,255,255,.5)' }}>
                  {label}
                </button>
              );
            })}
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:gap-3 shrink-0">
          {run && (
            <span className="mono text-2xs text-white/50 hidden lg:inline">
              {run.receipt?.file} · {fmt.int(run.n_rows)} rows · {run.duration_s}s
            </span>
          )}
          {health && (
            <span className="mono text-2xs flex items-center gap-1.5 text-white/70"
                  title="No network calls are made at any point">
              <span className="w-1.5 h-1.5 inline-block" style={{ background: 'var(--confirm)' }} />
              OFFLINE
            </span>
          )}
          <ThemeToggle />
          <input ref={fileRef} type="file" accept=".csv,.json,.jsonl,.xml" className="hidden"
                 onChange={(e) => onFile(e.target.files?.[0])} />
          <button onClick={() => fileRef.current?.click()} disabled={running}
                  className="mono text-xs px-2.5 h-7 inline-flex items-center gap-1.5 border
                             border-white/35 hover:bg-white/10 transition-colors duration-150
                             cursor-pointer disabled:opacity-40">
            <IconUpload /> <span className="hidden sm:inline">load capture</span>
          </button>
        </div>
      </header>

      {/* ---------------- run progress ---------------- */}
      {running && (
        <div className="bg-fusion-wash border-b border-rule px-3.5 py-2">
          <div className="flex items-center gap-3 mb-1.5">
            <Spinner label={`scoring ${job?.file}`} />
            <span className="mono text-2xs text-ink-dim">stage {job?.stage}</span>
          </div>
          <div className="flex gap-0.5">
            {STAGES.map((s, i) => (
              <div key={s} className="flex-1 relative overflow-hidden h-1.5 bg-surface-3"
                   title={s}>
                <div className="h-full transition-all duration-200"
                     style={{
                       width: i < stageIdx ? '100%' : i === stageIdx ? '55%' : '0%',
                       background: 'var(--fusion)',
                     }} />
              </div>
            ))}
          </div>
          <div className="flex justify-between mono text-2xs text-ink-dim mt-1">
            {STAGES.map((s) => <span key={s} className="flex-1 truncate">{s}</span>)}
          </div>
        </div>
      )}

      {job?.state === 'error' && (
        <div className="p-3">
          <Notice title="Run failed" layer="danger">
            <span className="mono">{job.error}</span>
          </Notice>
        </div>
      )}

      {/* ---------------- body ---------------- */}
      <main className="flex-1 min-h-0">
        {!run && !running ? (
          <div className="p-4 max-w-3xl">
            <Notice title="No capture scored yet">
              <p className="mb-3">
                Load a CSV, JSON or XML capture to score it, or run the bundled sample.
                The system is fully offline: no API, no node, no cloud model.
              </p>
              <div className="flex gap-2">
                <Button onClick={runSample}>run bundled sample</Button>
                <Button variant="ghost" onClick={() => fileRef.current?.click()}>
                  choose a file
                </Button>
              </div>
            </Notice>
          </div>
        ) : view.entity ? (
          <CaseFile entity={view.entity} onBack={() => go('alerts')} />
        ) : view.tab === 'model' ? (
          <ModelPanel />
        ) : view.tab === 'provenance' ? (
          <Provenance />
        ) : (
          <AlertQueue onOpen={(e) => go('alerts', e)} />
        )}
      </main>

      {/* ---------------- status bar ---------------- */}
      <footer className="bg-surface border-t border-rule px-3.5 py-1.5 flex flex-wrap
                         items-center gap-x-5 gap-y-1 shrink-0 no-print">
        <span className="text-2xs text-ink-dim">
          SIH 2026 · PS 26146 · NTRO · Blockchain &amp; Cybersecurity
        </span>

        {/* The layer palette is the one thing in this interface a viewer cannot
            infer. It was documented only in a CSS comment, so every coloured
            rule and figure on every screen was undecodable by design. */}
        <span className="flex items-center gap-3" aria-label="Colour key">
          {([['chain', 'chain layer'], ['network', 'network layer'],
             ['fusion', 'model output'], ['confirm', 'analyst action']] as const)
            .map(([k, label]) => (
              <span key={k} className="flex items-center gap-1.5 text-2xs text-ink-dim">
                <span aria-hidden className="w-2 h-2 inline-block"
                      style={{ background: `var(--${k})` }} />
                {label}
              </span>
            ))}
        </span>
        {run?.receipt?.attribution && (
          <span className="text-2xs text-ink-dim">
            attribution: {String((run.receipt.attribution as any).n_pairs_significant ?? 0)} significant
            of {String((run.receipt.attribution as any).n_pairs_tested ?? 0)} pairs tested
            · FDR α {String((run.receipt.attribution as any).fdr_alpha ?? '—')}
          </span>
        )}
        {health?.backend && (
          <span className="ml-auto text-2xs text-ink-dim">
            model backend {health.backend}
          </span>
        )}
      </footer>
    </div>
  );
}
