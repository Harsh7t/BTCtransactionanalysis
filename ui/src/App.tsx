/** Application shell.
 *
 * Dark chrome, dense light body — the arrangement Plates 04-06 specify. Routing
 * is the URL hash: four screens and a case-file deep link do not justify a
 * router dependency, and a real hash means an analyst can bookmark a case and
 * the browser back button behaves.
 */
import { useCallback, useEffect, useState } from 'react';
import { ThemeToggle } from './ThemeToggle';
import { api, fmt, type Job, type Run } from './api';
import { Notice } from './ui';
import { AlertQueue } from './components/AlertQueue';
import { StartScreen } from './components/StartScreen';
import { Processing } from './components/Processing';
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

export default function App() {
  const [view, setView] = useState<View>(parseHash);
  const [run, setRun] = useState<Run | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [entered, setEntered] = useState(false);
  const [runReady, setRunReady] = useState(false);

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
        if (j.state === 'done') { refresh(); setRunReady(true); window.location.hash = '#/alerts'; }
      }).catch(() => {});
    }, 400);
    return () => clearInterval(id);
  }, [job, refresh]);

  const go = (tab: View['tab'], entity?: string) => {
    window.location.hash = entity ? `#/case/${encodeURIComponent(entity)}` : `#/${tab}`;
  };



  const goHome = useCallback(() => {
    setEntered(false); setRunReady(false);
    window.location.hash = '#/alerts';
  }, []);

  // The header is transparent at rest and only takes a ground once something is
  // scrolled under it.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const running = job?.state === 'running';
  const showingStart = !running && (!entered || (!runReady && view.tab !== 'model'));

  // The landing no longer pins itself to the viewport: it has an explainer under
  // the fold, so the PAGE scrolls there the way it does on the queue - which is
  // also what makes the header's scrolled-ground state work there. Only the
  // scoring screen still owns its own height.
  return (
    <div className={`flex flex-col ${running ? 'h-full' : 'min-h-full'}`}>
      {/* ---------------- chrome ---------------- */}
      {/* The chrome bar is gone. It used to be a solid near-black slab sitting ON
          the page; now the header is the page - transparent, separated by one
          hairline, so on the landing the diffusion field runs straight through
          it and the whole screen reads as a single surface.

          It gains a ground only once the content scrolls under it, because a
          transparent bar over moving text is unreadable the moment you scroll. */}
      <header className={`sticky top-0 z-30 shrink-0 h-12 flex items-center gap-2 sm:gap-4
                          px-3 sm:px-6 border-b transition-colors duration-200
                          ${scrolled ? 'bg-surface border-rule' : 'bg-transparent border-transparent'}`}>
        {/* The masthead is the way home. During a run it is not: the scoring
            screen takes precedence over the landing anyway, so leaving it
            enabled would be a click that appears to do nothing. */}
        <button onClick={goHome} disabled={running}
                aria-label={running ? 'BTC-Fusion — a run is in progress'
                                    : 'BTC-Fusion — back to start'}
                title={running ? 'Scoring in progress' : 'Back to start'}
                className="flex items-baseline gap-2 shrink-0 cursor-pointer group
                           disabled:cursor-default">
          {/* Archivo 700, sentence case. The all-caps extrabold read as a logo
              bolted onto the page; this reads as a masthead. */}
          <span className="font-cond font-bold text-lg tracking-tight text-ink
                           transition-colors duration-150
                           group-enabled:group-hover:text-chain">
            BTC<span className="text-chain">·</span>Fusion
          </span>
          <span className="text-2xs text-ink-dim hidden md:inline">
            network ⇄ chain attribution
          </span>
        </button>

        <nav className="flex items-center gap-0.5 ml-1 sm:ml-3 min-w-0 overflow-x-auto
                        [scrollbar-width:none] [&::-webkit-scrollbar]{display:none}" aria-label="Main">
          {([['alerts', 'Alerts'], ['model', 'Model'], ['provenance', 'Provenance']] as const)
            .filter(([t]) => t === 'model' || runReady)
            .map(([t, label]) => {
              const active = entered && view.tab === t && !(t === 'alerts' && view.entity);
              return (
                <button key={t}
                        onClick={() => { setEntered(true); go(t); }}
                        aria-current={active ? 'page' : undefined}
                        className={`text-sm px-2 sm:px-3 h-12 border-b-2 cursor-pointer
                                    transition-colors duration-150
                                    ${active ? 'border-ink text-ink'
                                             : 'border-transparent text-ink-dim hover:text-ink-soft'}`}>
                  {label}
                </button>
              );
            })}
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:gap-3 shrink-0">
          {run && runReady && (
            <span className="mono text-2xs text-ink-dim hidden lg:inline">
              {run.receipt?.file} · {fmt.int(run.n_rows)} rows · {run.duration_s}s
            </span>
          )}
          {health && (
            <span className="text-2xs hidden sm:flex items-center gap-2 text-ink-soft"
                  title="No network calls are made at any point">
              <span className="w-1.5 h-1.5 inline-block" style={{ background: 'var(--confirm)' }} />
              OFFLINE
            </span>
          )}
          <ThemeToggle />
        </div>
      </header>

      {/* The run progress strip that used to live here is gone. The scoring
          screen shows the same nine stages far better, and two progress
          indicators for one job is one too many - the eye has to decide which
          one is authoritative. */}

      {job?.state === 'error' && (
        <div className="p-3">
          <Notice title="Run failed" layer="danger">
            <span className="mono">{job.error}</span>
          </Notice>
        </div>
      )}

      {/* ---------------- body ---------------- */}
      <main className="flex-1 min-h-0 flex flex-col">
        {running && job ? (
          <Processing job={job} />
        ) : showingStart ? (
          <StartScreen
            onStarted={(job_id, file) => { setEntered(true); setJob({ job_id, state: 'running', stage: 'ingest', file }); }}
            lastRun={run ? { rows: run.n_rows, file: run.receipt?.file || '' } : null}
            onViewLast={() => { setEntered(true); setRunReady(true); go('alerts'); }}
          />
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
      <footer className="bg-surface border-t border-rule px-4 py-2 flex flex-wrap
                         items-center gap-x-6 gap-y-1 shrink-0 no-print">
        <span className="text-2xs text-ink-dim">
          SIH 2026 · PS 26146 · NTRO · Blockchain &amp; Cybersecurity
        </span>

        {/* The layer palette is the one thing in this interface a viewer cannot
            infer, so it is spelled out where they first meet it - the landing.
            Everywhere after that it collapses to four swatches with the words in
            a title: a reminder, not a legend re-taught on every screen. Four
            labels under all five screens is permanent chrome for a fact you
            learn once. */}
        <span className="flex items-center gap-3" aria-label="Colour key">
          {([['chain', 'chain layer'], ['network', 'network layer'],
             ['fusion', 'model output'], ['confirm', 'analyst action']] as const)
            .map(([k, label]) => (
              <span key={k} title={label}
                    className="flex items-center gap-2 text-2xs text-ink-dim">
                <span aria-hidden className="w-2 h-2 inline-block"
                      style={{ background: `var(--${k})` }} />
                <span className={showingStart ? '' : 'sr-only'}>{label}</span>
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
