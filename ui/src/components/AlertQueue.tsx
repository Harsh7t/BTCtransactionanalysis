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
import { api, fmt, type Alert, type Receipt, type TxRow } from '../api';
import { Bar, Button, Chip, Counter, Eyebrow, IconFilter, Notice, Panel, Spinner, Stat, Tag } from '../ui';

const TYPOLOGIES = ['peel_chain', 'fan_out_in', 'rapid_layering',
  'mixer_passthrough', 'dormancy_burst', 'cross_asn_structuring'];

export function IngestReceipt({ r }: { r: Receipt }) {
  const q = r.rows_quarantined ?? 0;
  return (
    <Panel pad={false} className="mb-3">
      <div className="flex flex-wrap items-end gap-x-7 gap-y-3 px-3.5 py-3">
        {/* The headline claim of the whole demo, finally set at headline size.
            Six equal-weight stats gave the eye nowhere to land: the largest
            element on this screen used to be the 16px wordmark. */}
        <Stat label="records ingested" size="lead"
              value={<Counter value={r.rows_read} format={(n) => fmt.int(Math.round(n))} />}
              sub={`${r.format.toUpperCase()} · ${r.file}`} />
        <Stat label="elapsed" size="lead" layer="confirm"
              value={<><Counter value={r.duration_s} decimals={2} duration={900} />s</>}
              sub={`${fmt.int(r.rows_per_second)} rows/s`} />
        <Stat label="quarantined" value={fmt.int(q)} layer={q > 0 ? 'danger' : undefined}
              sub={q > 0 ? Object.keys(r.quarantine_breakdown).join(', ') : 'no rows rejected'} />
        <Stat label="duplicates" value={fmt.int(r.duplicates_removed)}
              sub="same txid·src·dst·ts" />
        <Stat label="entities resolved" value={fmt.int(r.n_entities_resolved)}
              sub={`${fmt.int(r.n_entities_active)} with activity`} />
        <Stat label="transactions" value={fmt.int(r.n_transactions)}
              sub={`${fmt.int(r.n_graph_edges)} graph edges`} />
        <div className="ml-auto flex items-center gap-2">
          {r.chain_only_mode
            ? <Tag layer="danger" title="No usable src_ip column in this capture">chain-only mode</Tag>
            : <Tag layer="network">network layer active</Tag>}
          {r.degraded_no_model
            ? <Tag layer="danger" title="No trained artefacts — unsupervised only">no model</Tag>
            : null}
        </div>
      </div>
      {/* Stage timings, inline. "500k records, 15 seconds" is a claim judges repeat. */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-rule-soft bg-surface-2 px-3.5 py-1.5">
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
    </Panel>
  );
}

type SortKey = 'rank' | 'confidence' | 'novelty' | 'total_out' | 'n_ips';

/* Column widths are declared here rather than inline because the ratios matter:
   typology previously took 338px - the widest column in the table - to hold two
   short tags, which pushed confidence and attribution into the right third and
   left a long empty gap for the eye to cross. */
const COLUMNS: { key: string; label: string; align: string; width: string; sort?: SortKey }[] = [
  { key: 'rank',  label: '#',           align: 'text-right', width: 'w-12',  sort: 'rank' },
  { key: 'ent',   label: 'entity',      align: 'text-left',  width: 'w-52' },
  { key: 'typ',   label: 'typology',    align: 'text-left',  width: 'w-56' },
  { key: 'conf',  label: 'confidence',  align: 'text-left',  width: 'w-52', sort: 'confidence' },
  { key: 'nov',   label: 'novelty',     align: 'text-right', width: 'w-20', sort: 'novelty' },
  { key: 'attr',  label: 'attribution', align: 'text-left',  width: 'w-44' },
  { key: 'val',   label: 'value moved', align: 'text-right', width: 'w-36', sort: 'total_out' },
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
  const [cursor, setCursor] = useState(0);
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
      } else if (e.key === 'Escape' && document.activeElement === searchRef.current) {
        setQuery('');
        searchRef.current?.blur();
      } else if ((e.key === 'j' || e.key === 'k') && tag !== 'INPUT') {
        e.preventDefault();
        setCursor((c) => Math.max(0, c + (e.key === 'j' ? 1 : -1)));
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

  // Keep the keyboard cursor in range and scrolled into view.
  useEffect(() => {
    const el = document.querySelector<HTMLTableRowElement>(`tr[data-row="${cursor}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [cursor]);

  useEffect(() => {
    if (level !== 'transactions') return;
    api.transactions(0, 200).then((r) => setTxRows(r.transactions)).catch(() => {});
  }, [level]);

  const suppressed = alerts.filter((a) => a.confidence < threshold).length;
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
      <IngestReceipt r={receipt} />

      <div className="flex items-center gap-0.5 mb-2.5" role="tablist"
           aria-label="Alert granularity">
        {(['entities', 'transactions'] as const).map((l) => (
          <button key={l} role="tab" aria-selected={level === l}
                  onClick={() => setLevel(l)}
                  className="mono text-xs px-3 h-7 border transition-colors duration-150 cursor-pointer"
                  style={level === l
                    ? { borderColor: 'var(--ink)', background: 'var(--ink)', color: '#fff' }
                    : { borderColor: 'var(--rule)', color: 'var(--ink-soft)' }}>
            {l}
          </button>
        ))}
        <span className="mono text-2xs text-ink-dim ml-2.5">
          {level === 'entities'
            ? 'wallet clusters \u2014 the investigative unit'
            : 'individual TXIDs, scored by the transaction head'}
        </span>
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
      {/* --- heading + search ---------------------------------------------- */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 mb-3">
        <h1 className="display text-ink">alert queue</h1>
        <span className="text-sm text-ink-soft">
          <span className="mono font-semibold text-ink">{visible.length}</span> leads ranked by the classifier
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-2xs text-ink-dim hidden lg:inline">
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

      {/* --- filters ------------------------------------------------------- */}
      <div className="flex flex-wrap items-center gap-2 mb-2.5">
        <span className="colhead flex items-center gap-1.5"><IconFilter className="w-3 h-3" />filters</span>
        <Chip active={!typology} onClick={() => setTypology('')}>
          all typologies <span className="opacity-60">{alerts.length}</span>
        </Chip>
        {TYPOLOGIES.map((t) => {
          const n = alerts.filter((a) => a.typologies.includes(t)).length;
          return (
            <Chip key={t} active={typology === t} disabled={n === 0}
                  onClick={() => setTypology(typology === t ? '' : t)}>
              {fmt.typology(t)} <span className="opacity-60">{n}</span>
            </Chip>
          );
        })}
        {asnTypes.length > 0 && <span className="w-px h-5 bg-rule mx-1" />}
        {asnTypes.map((t) => {
          const n = alerts.filter((a) => a.top_asn_type === t).length;
          return (
            <Chip key={t} layer="network" active={asnType === t}
                  onClick={() => setAsnType(asnType === t ? '' : t)}>
              {t} <span className="opacity-60">{n}</span>
            </Chip>
          );
        })}
        <Chip layer="confirm" active={unreviewed} onClick={() => setUnreviewed(!unreviewed)}>
          unreviewed only
        </Chip>

        {/* Live threshold with the trade-off stated, not implied. */}
        {/* `ml-auto` alone pinned this group to the right of a wrapping row, so
            on a narrow viewport it was pushed past the edge instead of wrapping
            under. `w-full` at mobile gives it its own line. */}
        <div className="w-full lg:w-auto lg:ml-auto flex items-center gap-2.5">
          <label htmlFor="thr" className="colhead">confidence threshold</label>
          <input id="thr" type="range" min={0.05} max={0.95} step={0.05} value={threshold}
                 className="w-40"
                 onChange={(e) => setThreshold(Number(e.target.value))} />
          <span className="mono text-md font-semibold w-9 text-fusion">{threshold.toFixed(2)}</span>
          <span className="text-2xs text-ink-dim w-28 shrink-0">
            {visible.length} shown · {suppressed} below
          </span>
        </div>
      </div>

      {/* --- queue --------------------------------------------------------- */}
      <Panel pad={false}>
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
                  {c.label}
                  {c.sort ? (
                    <span className={`ml-1 ${sort.key === c.sort ? 'text-ink' : 'text-rule'}`}>
                      {sort.key === c.sort ? (sort.dir === 'asc' ? '▲' : '▼') : '⇅'}
                    </span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((a, ri) => {
              const below = a.confidence < threshold;
              const typs = a.typologies ? a.typologies.split('|').filter(Boolean) : [];
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
                      ${below ? 'opacity-55' : ''}
                      ${ri === cursor ? 'bg-chain-wash outline outline-1 -outline-offset-1 outline-chain' : ''}`}>
                  <td className="px-3 py-1.5 align-top num">
                    {/* Right-aligned: left-aligned ranks put the units digit of 1,
                        10 and 60 in three different places. */}
                    <span className={a.rank <= 3
                      ? 'mono text-lg font-semibold text-ink'
                      : 'mono text-sm text-ink-dim'}>{a.rank}</span>
                  </td>
                  <td className="px-3 py-1.5 align-top">
                    <div className="mono text-md font-semibold text-ink whitespace-nowrap">{a.entity}</div>
                    <div className="text-2xs whitespace-nowrap flex items-center gap-1">
                      <span className="text-chain"><span className="mono">{fmt.int(a.n_addresses)}</span> addr</span>
                      <span className="text-rule">·</span>
                      <span className="text-chain"><span className="mono">{fmt.int(a.n_tx)}</span> tx</span>
                      <span className="text-rule">·</span>
                      <span className="text-network"><span className="mono">{fmt.int(a.n_ips)}</span> IP</span>
                    </div>
                  </td>
                  <td className="px-3 py-1.5 align-top max-w-[16rem]">
                    {a.raised_by === 'novelty' ? (
                      <Tag layer="network"
                           title="The classifier ranked this low; the novelty detector ranked it high. Reserved-slot alert - the answer to typologies nobody labelled.">
                        no typology match · unsupervised
                      </Tag>
                    ) : typs.length ? (
                      <div className="flex flex-wrap gap-1">
                        {typs.map((t) => <Tag key={t} layer="fusion">{fmt.typology(t)}</Tag>)}
                      </div>
                    ) : (
                      /* "no rule matched" read as a failure on ranks 1 and 2 -
                         the two highest-scoring entities in the queue. The model
                         ranked them top without a named pattern, which is the
                         system working, not failing. Say that. */
                      <Tag layer="data"
                           title="The classifier scored this highly on learned behaviour, but none of the six named laundering typologies matched. Open the case file for the SHAP reasons.">
                        model-only · no named typology
                      </Tag>
                    )}
                  </td>
                  <td className="px-3 py-1.5 align-top">
                    {/* A magnitude bar over a constant is noise. Scores across this
                        whole queue span 0.961-0.999, so 56 of 60 bars were pixel
                        identical and the column carried no information at all.
                        What DOES vary is the decomposition - novelty runs
                        0.48-1.00 - so the bar now shows that instead. */}
                    <div className="flex items-baseline gap-2">
                      <span className="mono text-md font-semibold">{fmt.conf(a.confidence)}</span>
                      <span className="text-2xs text-ink-dim">±{fmt.conf(a.interval)}</span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-1"
                         title={`supervised ${fmt.conf(a.supervised)} · novelty ${fmt.conf(a.novelty)}`}>
                      <span className="colhead" style={{ letterSpacing: '.04em' }}>sup</span>
                      <Bar value={a.supervised} layer="fusion" width={44} height={6}
                           delay={Math.min(a.rank, 14) * 18} />
                      <span className="colhead" style={{ letterSpacing: '.04em' }}>nov</span>
                      <Bar value={a.novelty} layer="network" width={44} height={6}
                           delay={Math.min(a.rank, 14) * 18 + 60} />
                    </div>
                  </td>
                  <td className="px-3 py-1.5 align-top num">
                    <span className="mono text-sm text-network">{fmt.conf(a.novelty)}</span>
                  </td>
                  <td className="px-3 py-1.5 align-top">
                    {a.attribution_status === 'ok' && a.top_asn ? (
                      <>
                        {/* 4 rows in 60. This is the product's entire thesis
                            landing, and it used to be styled identically to the
                            54 rows where attribution failed. */}
                        <div className="inline-flex flex-col border-l-2 pl-2"
                             style={{ borderColor: 'var(--network)' }}>
                          <span className="mono text-md font-semibold text-network whitespace-nowrap">
                            AS{a.top_asn}
                          </span>
                          <span className="text-2xs text-ink-soft whitespace-nowrap">
                            {a.top_asn_type} · {a.top_country} · conf{' '}
                            <span className="mono">{fmt.conf(a.attribution_confidence)}</span>
                          </span>
                        </div>
                      </>
                    ) : (
                      /* The constant case whispers: a glyph and one quiet word,
                         with the full reason on hover. Suppression is a correct
                         outcome, not a failure, and it does not need to shout
                         54 times to say so. */
                      <div className="text-2xs text-ink-dim flex items-center gap-1.5"
                           title={a.attribution_status === 'suppressed'
                             ? 'Attribution suppressed: the announcing IPs belong to shared infrastructure, so naming an owner would be a guess.'
                             : 'No entity-IP association survived FDR control.'}>
                        <span aria-hidden className="text-rule">—</span>
                        {a.attribution_status === 'suppressed' ? 'suppressed'
                          : a.attribution_status === 'no_significant_link' ? 'no link'
                          : a.attribution_status}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-1.5 align-top num">
                    <div className="mono text-md font-semibold whitespace-nowrap text-chain">
                      ₿ {fmt.btc(a.total_out)}
                    </div>
                    <div className="text-2xs text-ink-dim whitespace-nowrap">
                      in <span className="mono">₿ {fmt.btc(a.total_in)}</span>
                    </div>
                  </td>
                  <td className="px-2 py-1.5 align-top">
                    {a.verdict
                      ? <Tag layer={a.verdict === 'confirmed' ? 'confirm' : 'data'}>{a.verdict}</Tag>
                      : null}
                  </td>
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
        <div className="flex items-start gap-5 px-3.5 py-3">
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
