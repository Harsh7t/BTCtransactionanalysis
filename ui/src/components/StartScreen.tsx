/** The landing screen: the instrument at rest, waiting for a capture.
 *
 * Deliberately not a centred hero over a gradient. This is an asymmetric plate -
 * the argument and the controls on the left, a live diffusion field on the
 * right - because that is what the submitted wireframes look like and because a
 * forensics tool should read as apparatus rather than as a product page.
 *
 * The right-hand animation is the product's own thesis, not ornament: see
 * Propagation.tsx.
 */
import { useCallback, useRef, useState } from 'react';
import { api, fmt } from '../api';
import { Propagation } from './Propagation';

const ACCEPT = ['.csv', '.json', '.jsonl', '.xml'];
const FIELDS = ['timestamp', 'src_ip', 'dst_ip', 'src_port', 'dst_port', 'txid',
  'input_addresses', 'output_addresses', 'input_amounts', 'output_amounts',
  'fee', 'script_type', 'geo_country', 'asn'];

export function StartScreen({ onStarted, lastRun, onViewLast }: {
  onStarted: (jobId: string, file: string) => void;
  lastRun: { rows: number; file: string } | null;
  onViewLast: () => void;
}) {
  const [over, setOver] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const send = useCallback(async (f: File) => {
    // Checked before the bytes move. A 240 MB upload that fails on extension at
    // the far end is a minute of the analyst's life for a one-line mistake.
    const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
    if (!ACCEPT.includes(ext)) {
      setErr(`${f.name} is not a capture this system reads. Accepted: ${ACCEPT.join(', ')}.`);
      return;
    }
    setErr(null); setBusy(f.name);
    try {
      const { job_id } = await api.upload(f);
      onStarted(job_id, f.name);
    } catch (e) { setBusy(null); setErr(String(e)); }
  }, [onStarted]);

  const runSample = useCallback(async (path?: string, label = 'bundled sample') => {
    setErr(null); setBusy(label);
    try {
      // Server-side: capture.csv is 241 MB and bulk.csv is 1 GB. Pushing those
      // through a browser file input to reach a server that already has them on
      // disk would be theatre with a failure mode.
      const { job_id } = await api.startRun(path);
      onStarted(job_id, label);
    } catch (e) { setBusy(null); setErr(String(e)); }
  }, [onStarted]);

  return (
    <div className="h-full grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      {/* ---------------------------------------------------------- left */}
      <div className="flex flex-col justify-center px-6 sm:px-10 py-10 max-w-2xl">
        <h1 className="display text-ink anim-rise" style={{ fontSize: 'clamp(30px,4.4vw,52px)' }}>
          Network <span className="text-chain">⇄</span> chain<br />attribution
        </h1>

        <p className="text-md text-ink-soft mt-4 max-w-[54ch] anim-rise"
           style={{ animationDelay: '80ms' }}>
          Every blockchain tool can tell you that money moved suspiciously. This one
          correlates the <span className="text-network font-semibold">network layer</span> —
          IP, port, timing — with the <span className="text-chain font-semibold">chain
          layer</span> to say <em>who moved it</em>, and refuses to guess when the evidence
          is shared infrastructure.
        </p>

        {/* ------------------------------------------------------ dropzone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false);
                           const f = e.dataTransfer.files?.[0]; if (f) send(f); }}
          onClick={() => fileRef.current?.click()}
          role="button" tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileRef.current?.click(); }}
          aria-label="Drop a capture file here, or click to choose one"
          className={`relative mt-7 border cursor-pointer transition-colors duration-150 anim-rise
                      ${over ? 'border-chain bg-chain-wash' : 'border-rule bg-surface hover:border-ink'}`}
          style={{ animationDelay: '160ms' }}
        >
          {/* Registration marks, not a dashed rounded rectangle with a cloud. */}
          {(['tl', 'tr', 'bl', 'br'] as const).map((c) => (
            <span key={c} aria-hidden
                  className="absolute w-2.5 h-2.5 border-ink"
                  style={{
                    top: c[0] === 't' ? -1 : undefined, bottom: c[0] === 'b' ? -1 : undefined,
                    left: c[1] === 'l' ? -1 : undefined, right: c[1] === 'r' ? -1 : undefined,
                    borderTopWidth: c[0] === 't' ? 2 : 0, borderBottomWidth: c[0] === 'b' ? 2 : 0,
                    borderLeftWidth: c[1] === 'l' ? 2 : 0, borderRightWidth: c[1] === 'r' ? 2 : 0,
                    borderStyle: 'solid',
                    color: over ? 'var(--chain)' : 'var(--ink)',
                  }} />
          ))}

          <div className="px-6 py-8 text-center">
            {busy ? (
              <div className="figure text-chain" style={{ fontSize: 26 }}>{busy}</div>
            ) : (
              <>
                <div className="font-cond font-extrabold uppercase tracking-tight text-ink"
                     style={{ fontSize: 22 }}>
                  {over ? 'release to ingest' : 'drop a capture'}
                </div>
                <div className="text-sm text-ink-soft mt-1">
                  or click to choose · CSV, JSONL, XML
                </div>
              </>
            )}
          </div>
          <input ref={fileRef} type="file" accept={ACCEPT.join(',')} className="hidden"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) send(f); }} />
        </div>

        {err && (
          <p className="text-sm text-danger mt-2.5 anim-rise" role="alert">{err}</p>
        )}

        {/* -------------------------------------------------- sample runs */}
        <div className="mt-5 anim-rise" style={{ animationDelay: '240ms' }}>
          <div className="colhead mb-1.5">or score a bundled capture — no upload</div>
          <div className="flex flex-wrap gap-2">
            {[
              { name: 'judge.csv', label: 'judge', note: '16 MB · seconds' },
              { name: 'capture.csv', label: 'demo', note: '564k rows · 13 s' },
              { name: 'bulk.csv', label: 'bulk', note: '2.47M rows · 105 s' },
            ].map((s) => (
              <button key={s.name} disabled={!!busy}
                      onClick={() => runSample(`data/samples/${s.name}`, s.name)}
                      className="text-left border border-rule bg-surface px-3 py-2 cursor-pointer
                                 transition-colors duration-150 hover:border-ink
                                 disabled:opacity-40 disabled:cursor-default">
                <div className="font-cond font-bold uppercase text-ink text-sm tracking-tight">
                  {s.label}
                </div>
                <div className="text-2xs text-ink-dim mono">{s.note}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-2xs text-ink-dim
                        anim-rise" style={{ animationDelay: '320ms' }}>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-1.5 h-1.5 inline-block bg-confirm" />
            runs entirely offline — no API, no cloud model
          </span>
          <span title={FIELDS.join(', ')} className="cursor-help">
            expects <span className="mono text-ink-soft">{FIELDS.length}</span> fields ·
            hover to list
          </span>
          {lastRun && (
            <button onClick={onViewLast}
                    className="text-chain hover:underline cursor-pointer">
              view last run instead ({fmt.int(lastRun.rows)} rows)
            </button>
          )}
        </div>
      </div>

      {/* --------------------------------------------------------- right */}
      <div className="relative hidden lg:block border-l border-rule bg-surface-2 overflow-hidden">
        <Propagation className="absolute inset-0 w-full h-full" />
        <div className="absolute left-5 bottom-5 max-w-[42ch] pointer-events-none">
          <div className="colhead mb-1">live: randomised diffusion</div>
          <p className="text-2xs text-ink-soft leading-relaxed">
            One peer announces a transaction; the rest relay it after a
            <span className="text-ink"> randomised per-peer delay</span>. That delay is
            why first-seen attribution has been wrong since 2015 — and why this system
            uses a significance test over many announcements instead.
          </p>
        </div>
      </div>
    </div>
  );
}
