/** Plate 04 — the landing screen.
 *
 * Half a million records reduced to a handful of ranked leads. Two things are
 * load-bearing and both come straight from the wireframe:
 *
 *   THE INGEST RECEIPT sits above everything, so the analyst knows exactly what
 *   was and was not parsed before they trust a single row. A tool that quietly
 *   drops rows is worse than one that refuses to run.
 *
 *   THE SUPPRESSED FOOTER states how many entities scored below the threshold
 *   and what lowering it would cost in precision. The queue is a decision with
 *   a trade-off attached, not a list.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api, fmt, type Alert, type Receipt, type TxRow } from '../api';
import { Bar, Button, Chip, Counter, Eyebrow, IconFilter, Notice, Panel, Spinner, Stat, Tag } from '../ui';

const TYPOLOGIES = ['peel_chain', 'fan_out_in', 'rapid_layering',
  'mixer_passthrough', 'dormancy_burst', 'cross_asn_structuring'];

/** Drawn marks. Unicode arrows and triangles were standing in for an icon set,
 *  which puts the table's affordances at the mercy of whatever glyph the font
 *  happens to carry. One stroke weight, one grid. */
const mark = (d: ReactNode, w = 14) => (
  <svg viewBox="0 0 14 14" width={w} height={w} fill="none" stroke="currentColor"
       strokeWidth="1.5" strokeLinecap="square" aria-hidden>{d}</svg>
);
const ArrowRight = mark(<><path d="M2 7h9" /><path d="M8 4l3 3-3 3" /></>);
const SortNone = mark(<><path d="M4 6l3-3 3 3" /><path d="M4 8l3 3 3-3" /></>, 11);
const SortUp = mark(<path d="M3.5 9l3.5-4 3.5 4" />, 11);
const SortDown = mark(<path d="M3.5 5l3.5 4 3.5-4" />, 11);
const CheckMark = mark(<path d="M2.5 7.5 6 11l5.5-7" />, 12);
const ChevronRight = mark(<path d="M5.5 3.5 9 7l-3.5 3.5" />, 12);

/** The reduction, stated once, in the order it happens.
 *
 * This is the sentence the whole system exists to produce - a bulk capture
 * becomes a handful of leads - and it was nowhere on the screen. What stood here
 * instead was six equal-weight stat blocks and a stage-timing strip: 130px of
 * provenance that an analyst reads once, before the first lead, every time.
 *
 * Composed as a line rather than as three cards on purpose. Cards would make it
 * a dashboard header; the arrows make it a claim.
 */
function Funnel({ r, leads }: { r: Receipt; leads: number }) {
  const [open, setOpen] = useState(false);
  const q = r.rows_quarantined ?? 0;

  const step = (value: ReactNode, label: string, layer?: string) => (
    <div className="flex flex-col gap-0.5">
      <span className="figure" style={layer ? { color: `var(${layer})` } : undefined}>{value}</span>
      <span className="colhead">{label}</span>
    </div>
  );

  return (
    <Panel pad={false} className="mb-4">
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3 px-4 pt-3 pb-3">
        {step(<Counter value={r.rows_read} format={(n) => fmt.int(Math.round(n))} />,
              `${r.format.toUpperCase()} rows ingested`)}
        <span className="hidden sm:inline text-rule mb-2.5">{ArrowRight}</span>
        {step(fmt.int(r.n_entities_resolved), 'actors resolved', '--chain')}
        <span className="hidden sm:inline text-rule mb-2.5">{ArrowRight}</span>
        {step(fmt.int(leads), 'ranked leads', '--fusion')}

        <div className="ml-auto flex items-center gap-2 mb-1">
          {/* Only what can invalidate the run stays visible when closed. A zero
              quarantine count is not news; a non-zero one is. */}
          {q > 0 && <Tag layer="danger">{fmt.int(q)} quarantined</Tag>}
          {r.chain_only_mode
            ? <Tag layer="danger" title="No usable src_ip column in this capture">chain-only mode</Tag>
            : <Tag layer="network">network layer active</Tag>}
          {r.degraded_no_model
            ? <Tag layer="danger" title="No trained artefacts — unsupervised only">no model</Tag>
            : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule-soft
                      bg-surface-2 px-4 py-2">
        <span className="text-2xs text-ink-dim">
          <span className="mono text-ink">{r.file}</span> · scored in{' '}
          <span className="mono text-confirm font-semibold">
            <Counter value={r.duration_s} decimals={2} duration={900} />s
          </span>
          {' '}· <span className="mono">{fmt.int(r.rows_per_second)}</span> rows/s
        </span>
        <button onClick={() => setOpen(!open)} aria-expanded={open}
                className="ml-auto colhead flex items-center gap-1 hover:text-ink
                           transition-colors duration-150 cursor-pointer">
          ingest receipt
          <span className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}>
            {SortDown}
          </span>
        </button>
      </div>

      {open && (
        <div className="border-t border-rule-soft px-4 py-3">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
            <Stat label="quarantined" value={fmt.int(q)} layer={q > 0 ? 'danger' : undefined}
                  sub={q > 0 ? Object.keys(r.quarantine_breakdown).join(', ') : 'no rows rejected'} />
            <Stat label="duplicates" value={fmt.int(r.duplicates_removed)}
                  sub="same txid·src·dst·ts" />
            <Stat label="with activity" value={fmt.int(r.n_entities_active)}
                  sub="the analysis set" />
            <Stat label="transactions" value={fmt.int(r.n_transactions)}
                  sub={`${fmt.int(r.n_graph_edges)} graph edges`} />
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 pt-2 border-t border-rule-soft">
            <span className="colhead">stage timings</span>
            {(() => {
              const t = Object.entries(r.timings || {});
              const slowest = t.reduce((a, b) => (b[1] > a[1] ? b : a), t[0] || ['', 0])[0];
              return t.map(([k, v]) => (
                <span key={k} className={`text-2xs ${k === slowest ? 'text-ink' : 'text-ink-soft'}`}>
                  {k}{' '}
                  <span className={`mono font-semibold ${k === slowest ? 'text-fusion' : 'text-ink'}`}>
                    {v}s
                  </span>
                </span>
              ));
            })()}
          </div>
        </div>
      )}
    </Panel>
  );
}

/** What kind of evidence stands behind one lead, as three present/absent marks.
 *
 * The queue's hardest question to answer by eye was "why is this one here?", and
 * the answer was spread across three columns in three different visual
 * languages. These are one encoding, in the layer colours this codebase already
 * uses everywhere else: chain corroboration, a resolved network identity, and
 * the model's own call.
 *
 * The point is what it reveals when you scan the column rather than a row. On
 * this run 49 of 60 leads carry a named typology and exactly 3 carry an IP the
 * engine was willing to name - so the middle mark lights up three times in sixty
 * and the abstention the system is proud of becomes visible instead of implied.
 */
function Evidence({ a }: { a: Alert }) {
  const cells: [string, boolean, string][] = [
    ['--chain', Boolean(a.typologies),
     a.typologies ? `chain: ${a.typologies.split('|').filter(Boolean).map(fmt.typology).join(', ')}`
                  : 'chain: no named typology matched'],
    ['--network', a.attribution_status === 'ok' && Boolean(a.top_asn),
     a.attribution_status === 'ok' && a.top_asn
       ? `network: attributed to AS${a.top_asn}`
       : 'network: every candidate IP was shared infrastructure — suppressed, not guessed'],
    ['--fusion', true,
     a.raised_by === 'novelty'
       ? 'model: raised by the novelty detector, not the classifier'
       : 'model: ranked by the trained classifier'],
  ];
  return (
    <div className="flex items-center gap-1" role="img"
         aria-label={cells.map(([, on, t]) => (on ? t : `no ${t}`)).join('. ')}>
      {cells.map(([layer, on, title]) => (
        <span key={layer} title={title}
              className="w-2 h-4 inline-block"
              style={on
                ? { background: `var(${layer})` }
                : { background: 'transparent', boxShadow: 'inset 0 0 0 1px var(--rule)' }} />
      ))}
    </div>
  );
}

type SortKey = 'rank' | 'confidence' | 'novelty' | 'total_out' | 'n_ips';

/* Column widths are declared here rather than inline because the ratios matter:
   typology previously took 338px - the widest column in the table - to hold two
   short tags, which pushed confidence and attribution into the right third and
   left a long empty gap for the eye to cross. */
const COLUMNS: { key: string; label: string; align: string; width: string; sort?: SortKey }[] = [
  { key: 'rank',  label: '#',           align: 'text-right', width: 'w-10',  sort: 'rank' },
  { key: 'ev',    label: 'evidence',    align: 'text-left',  width: 'w-20' },
  { key: 'ent',   label: 'entity',      align: 'text-left',  width: 'w-56' },
  { key: 'typ',   label: 'pattern',     align: 'text-left',  width: 'w-52' },
  { key: 'attr',  label: 'attribution', align: 'text-left',  width: 'w-44' },
  { key: 'conf',  label: 'confidence',  align: 'text-right', width: 'w-28', sort: 'confidence' },
  { key: 'nov',   label: 'novelty',     align: 'text-right', width: 'w-16', sort: 'novelty' },
  { key: 'val',   label: 'value moved', align: 'text-right', width: 'w-48', sort: 'total_out' },
  { key: 'act',   label: '',            align: 'text-left',  width: 'w-8' },
];

export function AlertQueue({ onOpen }: { onOpen: (entity: string) => void }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0.55);
  const [typology, setTypology] = useState<string>('');
  const [asnType, setAsnType] = useState<string>('');
  const [unreviewed, setUnreviewed] = useState(false);
  const [showSuppressed, setShowSuppressed] = useState(false);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'rank', dir: 'asc' });
  // null until the user actually navigates. Starting at 0 painted row one as
  // selected the moment the page loaded, which claims a choice nobody made and
  // draws the eye to rank 1 as if it were special beyond simply being first.
  const [cursor, setCursor] = useState<number | null>(null);
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;
  const toggleSort = (key: SortKey) =>
    setSort((s0) => ({ key, dir: s0.key === key && s0.dir === 'asc' ? 'desc' : 'asc' }));
  const searchRef = useRef<HTMLInputElement>(null);
  // The PS asks why a wallet OR a transaction was flagged. Entities are the
  // investigative unit and stay the default; transactions are one click away.
  const [level, setLevel] = useState<'entities' | 'transactions'>('entities');
  const [txRows, setTxRows] = useState<TxRow[]>([]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    Promise.all([api.latestRun(), api.alerts({ min_confidence: 0 })])
      .then(([runRes, alertRes]) => {
        if (!live) return;
        setReceipt(runRes.run?.receipt ?? null);
        setAlerts(alertRes.alerts);
        if (runRes.run?.receipt?.threshold) setThreshold(runRes.run.receipt.threshold);
        setErr(null);
      })
      .catch((e) => live && setErr(String(e)))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = alerts.filter((a) =>
      (showSuppressed || a.confidence >= threshold)
      && (!typology || a.typologies.includes(typology))
      && (!asnType || a.top_asn_type === asnType)
      && (!unreviewed || !a.verdict)
      && (!q || a.entity.toLowerCase().includes(q))
    );
    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((x, y) => {
      const vx = sort.key === 'total_out' ? x.total_out
        : sort.key === 'n_ips' ? x.n_ips
        : sort.key === 'novelty' ? x.novelty
        : sort.key === 'confidence' ? x.confidence : x.rank;
      const vy = sort.key === 'total_out' ? y.total_out
        : sort.key === 'n_ips' ? y.n_ips
        : sort.key === 'novelty' ? y.novelty
        : sort.key === 'confidence' ? y.confidence : y.rank;
      return (vx - vy) * dir;
    });
  }, [alerts, threshold, typology, asnType, unreviewed, showSuppressed, query, sort]);

  // `/` focuses search, Escape clears it. Analysts in this genre live on the
  // keyboard; the queue previously had no shortcut of any kind.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA') {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === 'Escape') {
        if (document.activeElement === searchRef.current) {
          setQuery('');
          searchRef.current?.blur();
        }
        setCursor(null);
      } else if ((e.key === 'j' || e.key === 'k') && tag !== 'INPUT') {
        e.preventDefault();
        // First keypress selects the top row rather than moving from it.
        setCursor((c) => (c === null ? 0 : Math.max(0, c + (e.key === 'j' ? 1 : -1))));
      } else if (e.key === 'Enter' && tag !== 'INPUT' && tag !== 'BUTTON') {
        // Completes the keyboard loop: j/k to move, Enter to open. Without this
        // the cursor was a highlight that could not do anything.
        const row = document.querySelector<HTMLElement>('tr[data-open][data-cursor="1"]');
        const id = row?.getAttribute('data-open');
        if (id) { e.preventDefault(); onOpenRef.current(id); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Keep the keyboard cursor scrolled into view - but never scroll on mount.
  useEffect(() => {
    if (cursor === null) return;
    document.querySelector<HTMLTableRowElement>(`tr[data-row="${cursor}"]`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [cursor]);

  useEffect(() => {
    if (level !== 'transactions') return;
    api.transactions(0, 200).then((r) => setTxRows(r.transactions)).catch(() => {});
  }, [level]);

  const suppressed = alerts.filter((a) => a.confidence < threshold).length;
  // Scale the magnitude bars to the whole queue, not to what is currently
  // filtered: a bar that rescales as you type is not a comparison.
  const maxValue = useMemo(
    () => Math.max(1, ...alerts.map((a) => a.total_out || 0)), [alerts]);
  const asnTypes = useMemo(
    () => Array.from(new Set(alerts.map((a) => a.top_asn_type).filter(Boolean))), [alerts]);

  if (loading) return <div className="p-8"><Spinner label="loading alert queue…" /></div>;
  if (err) return <div className="p-4"><Notice title="Could not load alerts" layer="danger">{err}</Notice></div>;
  if (!receipt) return (
    <div className="p-4">
      <Notice title="No run yet">
        Load a capture to score it. Use <span className="mono">Load capture</span> above, or run{' '}
        <span className="mono">make run</span> from the repository root.
      </Notice>
    </div>
  );

  return (
    <div className="p-3">
      <Funnel r={receipt} leads={alerts.length} />

      {/* Granularity and search on one line. The display heading that used to sit
          below this said "alert queue" under a nav tab reading Alerts, beside a
          count the funnel states more precisely - three ways of saying the same
          thing, costing 50px above the first lead. */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <div className="flex items-center gap-0.5" role="tablist" aria-label="Alert granularity">
          {(['entities', 'transactions'] as const).map((l) => (
            <button key={l} role="tab" aria-selected={level === l}
                    onClick={() => setLevel(l)}
                    className="mono text-sm px-3 h-7 border transition-colors duration-150 cursor-pointer"
                    style={level === l
                      ? { borderColor: 'var(--ink)', background: 'var(--ink)', color: 'var(--paper)' }
                      : { borderColor: 'var(--rule)', color: 'var(--ink-soft)' }}>
              {l}
            </button>
          ))}
        </div>
        <span className="text-2xs text-ink-dim">
          {level === 'entities'
            ? 'wallet clusters \u2014 the investigative unit'
            : 'individual TXIDs, scored by the transaction head'}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-2xs text-ink-dim hidden xl:inline">
            <kbd className="mono">/</kbd> search · <kbd className="mono">j</kbd>
            <kbd className="mono">k</kbd> move · <kbd className="mono">↵</kbd> open
          </span>
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="find entity…  /"
            aria-label="Search by entity ID"
            className="h-7 w-52 bg-surface border border-rule px-2 mono text-sm
                       placeholder:text-ink-dim focus:border-ink outline-none"
          />
          {query ? (
            <button onClick={() => { setQuery(''); searchRef.current?.focus(); }}
                    className="h-7 px-2 text-2xs text-ink-soft border border-rule hover:border-ink">
              clear
            </button>
          ) : null}
        </div>
      </div>

      {level === 'transactions' ? (
        <Panel pad={false}>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse min-w-[56rem]">
              <thead>
                <tr className="border-b border-rule">
                  {['txid', 'entity', 'time', 'value', 'in/out', 'entropy', 'score'].map((h, i) => (
                    <th key={h} className={`eyebrow px-3 py-2 ${i >= 3 ? 'text-right' : 'text-left'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {txRows.map((t) => (
                  <tr key={t.txid} className="row-hover border-b border-rule-soft cursor-pointer">
                    <td className="px-3 py-2 mono text-sm">{t.txid.slice(0, 22)}…</td>
                    <td className="px-3 py-2 mono text-sm">
                      <button onClick={() => onOpen(t.entity)}
                              className="text-chain hover:underline cursor-pointer">{t.entity}</button>
                    </td>
                    <td className="px-3 py-2 mono text-2xs text-ink-dim">{fmt.time(String(t.ts))}</td>
                    <td className="px-3 py-2 num mono text-sm">₿ {fmt.btc(t.value_out)}</td>
                    <td className="px-3 py-2 num mono text-2xs">{t.n_inputs}/{t.n_outputs}</td>
                    <td className="px-3 py-2 num mono text-2xs">{(t.output_entropy ?? 0).toFixed(2)}</td>
                    <td className="px-3 py-2 num">
                      <div className="flex items-center gap-2 justify-end">
                        <Bar value={t.tx_score} width={70} height={8} />
                        <span className="mono text-md font-semibold">{fmt.conf(t.tx_score)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {txRows.length === 0 && (
            <div className="p-6 text-center text-sm text-ink-soft">
              No transaction-level scores in this run.
            </div>
          )}
        </Panel>
      ) : (<>
      {/* --- filters ------------------------------------------------------- */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="colhead flex items-center gap-2"><IconFilter className="w-3 h-3" />filters</span>
        <Chip active={!typology} onClick={() => setTypology('')}>
          all typologies <span className="opacity-60">{alerts.length}</span>
        </Chip>
        {/* A filter that matches nothing is not a filter, it is a disabled button
            taking up a slot. Thirteen chips wrapped onto two rows here; dropping
            the empty ones leaves only facets that can actually change the view. */}
        {TYPOLOGIES.map((t) => {
          const n = alerts.filter((a) => a.typologies.includes(t)).length;
          if (n === 0) return null;
          return (
            <Chip key={t} active={typology === t}
                  onClick={() => setTypology(typology === t ? '' : t)}>
              {fmt.typology(t)} <span className="opacity-60">{n}</span>
            </Chip>
          );
        })}
        {/* Host class is a second facet, and five more chips for it pushed the
            filter row onto two lines at every width. A native select holds the
            same five choices in one control, sorts itself, and needs no code. */}
        {asnTypes.length > 0 && (
          <>
            <span className="w-px h-5 bg-rule mx-1" />
            <label className="colhead" htmlFor="asn">host class</label>
            <select id="asn" value={asnType}
                    onChange={(e) => setAsnType(e.target.value)}
                    className="h-7 bg-surface border px-2 mono text-sm cursor-pointer
                               outline-none focus:border-ink"
                    style={{ borderColor: asnType ? 'var(--network)' : 'var(--rule)',
                             color: asnType ? 'var(--network)' : 'var(--ink-soft)' }}>
              <option value="">any</option>
              {asnTypes.map((t) => {
                const n = alerts.filter((a) => a.top_asn_type === t).length;
                return <option key={t} value={t}>{t} ({n})</option>;
              })}
            </select>
          </>
        )}
        <Chip layer="confirm" active={unreviewed} onClick={() => setUnreviewed(!unreviewed)}>
          unreviewed only
        </Chip>

      </div>

      {/* --- queue --------------------------------------------------------- */}
      <Panel pad={false}>
        {/* The threshold governs this table, so it sits on it. Sharing the filter
            row instead pushed that row to two lines at every viewport width and
            put a global control among per-facet toggles. */}
        <div className="flex items-center gap-3 px-3 py-2 border-b border-rule-soft bg-surface-2">
          <label htmlFor="thr" className="colhead">confidence threshold</label>
          <input id="thr" type="range" min={0.05} max={0.95} step={0.05} value={threshold}
                 className="w-40 accent-[var(--fusion)]"
                 onChange={(e) => setThreshold(Number(e.target.value))} />
          <span className="mono text-md font-semibold w-9 text-fusion">{threshold.toFixed(2)}</span>
          <span className="flex items-center gap-3 ml-auto text-2xs text-ink-dim">
            <span className="hidden xl:flex items-center gap-2">
              <span className="colhead">evidence</span>
              {([['--chain', 'chain'], ['--network', 'network'], ['--fusion', 'model']] as const)
                .map(([v, l]) => (
                  <span key={l} className="flex items-center gap-1">
                    <span className="w-2 h-3 inline-block" style={{ background: `var(${v})` }} />
                    {l}
                  </span>
                ))}
            </span>
            <span aria-hidden className="hidden xl:inline text-rule">|</span>
            <span>
              <span className="mono text-ink">{visible.length}</span> shown ·{' '}
              <span className="mono">{suppressed}</span> below
            </span>
          </span>
        </div>
        {/* The table needs 62rem. Below that it scrolls - which it always did,
            but silently: 65% of the columns were unreachable on a phone with no
            indication they existed. */}
        <div className="overflow-x-auto scroll-hint">
        <table className="w-full border-collapse min-w-[62rem]">
          <thead>
            <tr className="border-b border-rule">
              {COLUMNS.map((c) => (
                <th key={c.key}
                    onClick={c.sort ? () => toggleSort(c.sort!) : undefined}
                    aria-sort={c.sort && sort.key === c.sort
                      ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                    className={`colhead px-3 py-2 ${c.align} ${c.width}
                      ${c.sort ? 'cursor-pointer select-none hover:text-ink' : ''}`}>
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    {c.sort ? (
                      <span className={sort.key === c.sort ? 'text-ink' : 'text-ink-dim opacity-45'}>
                        {sort.key === c.sort
                          ? (sort.dir === 'asc' ? SortUp : SortDown)
                          : SortNone}
                      </span>
                    ) : null}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((a, ri) => {
              const below = a.confidence < threshold;
              const typs = a.typologies ? a.typologies.split('|').filter(Boolean) : [];
              const attributed = a.attribution_status === 'ok' && Boolean(a.top_asn);
              // Log, because value moved spans 24,224x across this queue - four
              // and a half orders of magnitude. A linear bar would render
              // fifty-nine leads as an empty track and one as full.
              const mag = maxValue > 1
                ? Math.log10(Math.max(a.total_out, 1)) / Math.log10(maxValue)
                : 0;
              return (
                <tr key={a.entity}
                    onClick={() => onOpen(a.entity)}
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter') onOpen(a.entity); }}
                    data-row={ri}
                    data-open={a.entity}
                    data-cursor={ri === cursor ? '1' : '0'}
                    style={{ animationDelay: `${Math.min(ri, 14) * 18}ms` }}
                    className={`anim-rise row-hover border-b border-rule-soft cursor-pointer
                      ${below ? 'opacity-50' : ''}
                      ${a.verdict === 'dismissed' ? 'opacity-40' : ''}
                      ${ri === cursor ? 'bg-chain-wash outline outline-1 -outline-offset-1 outline-chain' : ''}`}>

                  {/* Rank. The top three carry the model's strongest claim, so
                      they are the only ones set at size; below that the ordinal
                      is a reference, not a headline. */}
                  <td className="pl-3 pr-1 py-2.5 align-top num">
                    <span className={a.rank <= 3
                      ? 'mono text-lg font-semibold text-ink'
                      : 'mono text-sm text-ink-dim'}>{a.rank}</span>
                  </td>

                  <td className="px-3 py-2.5 align-top"><Evidence a={a} /></td>

                  {/* The identity, and what it is made of. This is the anchor of
                      the row: the one thing the analyst acts on. */}
                  <td className="px-3 py-2.5 align-top">
                    <div className="mono text-md font-semibold text-ink whitespace-nowrap
                                    flex items-center gap-2">
                      {a.entity}
                      {a.verdict === 'confirmed' && (
                        <span className="text-confirm" title="Confirmed by an analyst">{CheckMark}</span>
                      )}
                    </div>
                    <div className="text-2xs text-ink-dim whitespace-nowrap mt-0.5">
                      <span className="mono">{fmt.int(a.n_addresses)}</span> addr
                      <span aria-hidden className="text-rule"> · </span>
                      <span className="mono">{fmt.int(a.n_tx)}</span> tx
                      <span aria-hidden className="text-rule"> · </span>
                      <span className="mono">{fmt.int(a.n_ips)}</span> IP
                    </div>
                  </td>

                  {/* Pattern. Absent is the quiet case - a fifth of the queue has
                      no named typology, and a full tag on each made the widest
                      column a repeated statement about nothing. */}
                  <td className="px-3 py-2.5 align-top">
                    {a.raised_by === 'novelty' ? (
                      <Tag layer="network"
                           title="The classifier ranked this low; the novelty detector ranked it high. A reserved-slot alert — the answer to typologies nobody labelled.">
                        novelty slot
                      </Tag>
                    ) : typs.length ? (
                      <div className="flex flex-wrap gap-1">
                        {typs.map((t) => <Tag key={t} layer="fusion">{fmt.typology(t)}</Tag>)}
                      </div>
                    ) : (
                      <span className="text-sm text-ink-dim"
                            title="The classifier scored this highly on learned behaviour, but none of the six named laundering typologies matched. Open the case file for the SHAP reasons.">
                        model-only
                      </span>
                    )}
                  </td>

                  {/* Attribution. Three of sixty resolve, and this is the entire
                      thesis of the project landing on screen - so when it lands
                      it is the loudest thing in the row, and when it does not it
                      is the quietest. */}
                  <td className="px-3 py-2.5 align-top">
                    {attributed ? (
                      <div>
                        <div className="mono text-md font-semibold text-network whitespace-nowrap">
                          AS{a.top_asn}
                        </div>
                        <div className="text-2xs text-ink-soft whitespace-nowrap mt-0.5">
                          {a.top_asn_type} · {a.top_country} ·{' '}
                          <span className="mono">{fmt.conf(a.attribution_confidence)}</span>
                        </div>
                      </div>
                    ) : (
                      <span className="text-sm text-ink-dim"
                            title="Every candidate IP for this entity resolved to shared infrastructure. The engine suppressed the attribution rather than name someone on evidence that cannot carry it.">
                        <span aria-hidden className="text-rule">—</span>{' '}
                        {a.attribution_status === 'ok' ? 'no link' : 'suppressed'}
                      </span>
                    )}
                  </td>

                  {/* Confidence and its interval at the same weight. The
                      calibrator clips at 0.97, so 54 of 60 leads print 0.96 or
                      0.97 - measured - and the number that varies least used to
                      be the largest thing in the row. The interval spans
                      0.093-0.382 across the same queue, and that is the half
                      worth reading. */}
                  <td className="px-3 py-2.5 align-top num whitespace-nowrap">
                    <span className="mono text-md font-semibold">{fmt.conf(a.confidence)}</span>
                    <span className="mono text-2xs text-ink-soft ml-1">±{fmt.conf(a.interval)}</span>
                  </td>

                  <td className="px-3 py-2.5 align-top num">
                    <span className="mono text-sm text-network">{fmt.conf(a.novelty)}</span>
                  </td>

                  {/* Value moved, with the magnitude drawn. This is the one
                      quantity on the page with a real range, and length is the
                      channel the eye compares fastest. */}
                  <td className="px-3 py-2.5 align-top">
                    <div className="mono text-md font-semibold text-chain num">
                      {fmt.btc(a.total_out)}
                    </div>
                    {/* Right-anchored, so the bar ends where its number ends and
                        grows leftward. Left-anchored under a right-aligned figure,
                        the two read as unrelated objects. */}
                    <div className="flex justify-end mt-1.5"
                         title={`received ${fmt.btc(a.total_in)}`}>
                      <div className="h-1.5 anim-bar"
                           style={{ width: `${Math.max(3, mag * 100)}%`,
                                    background: 'var(--chain)',
                                    animationDelay: `${Math.min(ri, 14) * 18 + 90}ms` }} />
                    </div>
                  </td>

                  <td className="pl-1 pr-3 py-2.5 align-top text-ink-dim">{ChevronRight}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        </div>

        {visible.length === 0 && (
          <div className="p-6 text-center text-sm text-ink-soft">
            No alerts match these filters. Lower the threshold or clear a filter.
          </div>
        )}
      </Panel>

      </>)}

      {/* --- what we are NOT showing, and what it would cost to look -------- */}
      <Panel className="mt-3" pad={false}>
        <div className="flex items-start gap-6 px-4 py-3">
          <div className="flex-1">
            <Eyebrow>below threshold</Eyebrow>
            <p className="text-sm text-ink-soft max-w-[78ch]">
              <span className="mono font-semibold text-ink">{fmt.int(receipt.n_below_threshold)}</span>{' '}
              entities scored below {threshold.toFixed(2)} and are suppressed from the queue.
              Lowering the threshold surfaces more true positives and proportionally more
              false ones — the calibration curve in the Model panel shows the exact
              trade-off, measured rather than asserted.
            </p>
          </div>
          <Button variant={showSuppressed ? 'default' : 'ghost'}
                  onClick={() => setShowSuppressed(!showSuppressed)}>
            {showSuppressed ? 'hide suppressed' : 'show suppressed'}
          </Button>
        </div>
      </Panel>
    </div>
  );
}
