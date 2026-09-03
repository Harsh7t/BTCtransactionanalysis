/** Plate 05 — the output artefact.
 *
 * Not an alert: an investigative document that has to survive being forwarded to
 * someone who has never seen this tool. Assessment in English, calibrated
 * confidence, evidence with real TXIDs, the graph path, the timeline, and the
 * network attribution.
 *
 * THE COUNTERFACTUAL BLOCK is the single most important element on this screen.
 * Every dashboard shows a number; none of them show what would move it. Analysts
 * reason about what evidence would confirm or collapse a hypothesis, so the
 * system states that explicitly — and because those lines are computed by
 * re-running the confidence model with one input changed, they are a property of
 * the model rather than copywriting.
 */
import { useEffect, useState } from 'react';
import { api, fmt, type CaseFile as CF } from '../api';
import {
  Bar, Eyebrow, IconBack, IconCheck, IconExport, IconX, Notice, Panel, Spinner, Tag,
} from '../ui';
import { GraphView } from './GraphView';
import { HourHistogram, TxTimeline } from './Charts';

export function CaseFile({ entity, onBack }: { entity: string; onBack: () => void }) {
  const [d, setD] = useState<CF | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<string>('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setD(null); setErr(null);
    api.caseFile(entity)
      .then((r) => { if (live) { setD(r); setVerdict(r.alert.verdict || ''); } })
      .catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, [entity]);

  async function decide(v: string) {
    setBusy(true);
    try {
      await api.verdict(entity, v, v === 'dismissed' ? 'analyst dismissed from case file' : '');
      setVerdict(v);
    } finally { setBusy(false); }
  }

  if (err) return <div className="p-4"><Notice title="Could not load case file" layer="danger">{err}</Notice></div>;
  if (!d) return <div className="p-8"><Spinner label={`assembling case file for ${entity}…`} /></div>;

  const a = d.alert;
  // Candidates often share a counterfactual ("if the IPs resolve to a shared VPN"),
  // and a flat concat printed it once per candidate. Dedupe on the text itself.
  const counterfactuals = [...new Map(
    d.attribution.flatMap((c) => c.counterfactuals || []).map((c) => [c.text, c]),
  ).values()].slice(0, 4);
  const top = d.attribution[0];

  return (
    <div className="p-3">
      {/* --- case header ---------------------------------------------------- */}
      <div className="flex items-center gap-3 bg-ink text-white px-3 h-11 mb-3">
        <button onClick={onBack}
                className="mono text-xs flex items-center gap-1.5 hover:opacity-70 cursor-pointer transition-opacity duration-150">
          <IconBack /> alerts
        </button>
        <span className="w-px h-5 bg-white/25" />
        <span className="font-cond font-bold uppercase text-lg tracking-tight">
          Case file — {a.entity}
        </span>
        <span className="mono text-2xs text-white/55">rank {a.rank} · run {d.run_id}</span>
        <div className="ml-auto flex items-center gap-2 no-print">
          {verdict
            ? <Tag layer={verdict === 'confirmed' ? 'confirm' : 'data'}>{verdict}</Tag>
            : null}
          <a href={api.exportUrl(entity)} target="_blank" rel="noreferrer"
             className="mono text-xs px-2.5 h-7 inline-flex items-center gap-1.5 border border-white/35
                        text-white hover:bg-white/10 transition-colors duration-150">
            <IconExport /> export
          </a>
          <button onClick={() => decide('confirmed')} disabled={busy}
                  className="mono text-xs px-2.5 h-7 inline-flex items-center gap-1.5 text-white
                             transition-opacity duration-150 hover:opacity-85 cursor-pointer"
                  style={{ background: 'var(--confirm)' }}>
            <IconCheck /> confirm
          </button>
          <button onClick={() => decide('dismissed')} disabled={busy}
                  className="mono text-xs px-2.5 h-7 inline-flex items-center gap-1.5 border
                             border-white/35 text-white hover:bg-white/10 transition-colors duration-150">
            <IconX /> dismiss
          </button>
        </div>
      </div>

      {/* Asymmetric split, as the wireframe specifies: evidence reads as a
          column; the graph needs width. Equal halves would serve neither. */}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] gap-3">
        {/* ================= LEFT: the argument ============================ */}
        <div className="space-y-3 min-w-0">
          <Panel accent="fusion">
            <Eyebrow layer="fusion">assessment</Eyebrow>
            <p className="text-md leading-relaxed">{a.narrative}</p>
          </Panel>

          <Panel>
            <Eyebrow layer="fusion" right={`isotonic-calibrated`}>confidence</Eyebrow>
            <div className="flex items-end gap-3">
              <span className="font-cond font-bold text-4xl leading-none">{fmt.conf(a.confidence)}</span>
              <span className="mono text-sm text-ink-soft pb-1">± {fmt.conf(a.interval)}</span>
            </div>
            <div className="mt-2.5">
              <Bar value={a.confidence} layer="fusion" width="100%" height={10} />
            </div>
            <div className="flex gap-4 mt-2 mono text-2xs text-ink-dim">
              <span>supervised <b className="text-ink">{fmt.conf(a.supervised)}</b></span>
              <span>novelty <b className="text-ink">{fmt.conf(a.novelty)}</b></span>
              <span>evidence <b className="text-ink">{fmt.conf(a.evidence_strength)}</b></span>
            </div>

            {counterfactuals.length > 0 && (
              <div className="mt-3 border border-dashed border-rule bg-surface-2 p-3">
                <Eyebrow layer="network">what would change this</Eyebrow>
                <ul className="space-y-1.5">
                  {counterfactuals.map((c, i) => (
                    <li key={i} className="text-sm flex gap-2">
                      <span className="mono font-semibold shrink-0"
                            style={{ color: c.direction === 'down' ? 'var(--danger)' : 'var(--confirm)' }}>
                        {c.direction === 'down' ? '↓' : '↑'} {c.value.toFixed(2)}
                      </span>
                      <span className="text-ink-soft">{c.text.replace(/^(falls|rises) to [\d.]+ /, '')}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>

          {d.evidence.length > 0 && (
            <Panel>
              <Eyebrow layer="chain" right={`${d.evidence.length} matcher${d.evidence.length > 1 ? 's' : ''}`}>
                evidence chain
              </Eyebrow>
              <div className="space-y-2.5">
                {d.evidence.map((e, i) => (
                  <div key={i} className="border border-rule-soft bg-surface-2">
                    <div className="flex items-center gap-2 px-2.5 py-1.5 border-b border-rule-soft">
                      <Tag layer="fusion">{fmt.typology(e.typology)}</Tag>
                      <span className="mono text-2xs text-ink-dim">strength {e.strength.toFixed(2)}</span>
                    </div>
                    <p className="px-2.5 py-2 text-sm text-ink-soft">{e.summary}</p>
                    {e.detail?.length > 0 && (
                      <table className="w-full border-t border-rule-soft">
                        <tbody>
                          {e.detail.map((row, j) => (
                            <tr key={j} className="border-b border-rule-soft last:border-0">
                              {Object.entries(row).map(([k, v]) => (
                                <td key={k} className="px-2.5 py-1 mono text-2xs">
                                  <span className="text-ink-dim">{k.replace(/_/g, ' ')} </span>
                                  <span className="text-ink">{String(v).length > 24
                                    ? `${String(v).slice(0, 22)}…` : String(v)}</span>
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                ))}
              </div>
              <p className="mono text-2xs text-ink-dim mt-2">
                Matchers attach corroboration to a model-raised alert. They never raise one.
              </p>
            </Panel>
          )}

          {d.shap.length > 0 && (
            <Panel>
              <Eyebrow layer="fusion" right="exact · TreeExplainer">model attributions (SHAP)</Eyebrow>
              <table className="w-full">
                <tbody>
                  {d.shap.slice(0, 8).map((s) => (
                    <tr key={s.feature} className="border-b border-rule-soft last:border-0">
                      <td className="mono text-2xs py-1.5 pr-2 w-48 truncate" title={s.feature}>
                        {s.feature}
                      </td>
                      <td className="py-1.5 w-32">
                        <Bar value={Math.abs(s.contribution)}
                             max={Math.abs(d.shap[0].contribution) || 1}
                             negative={s.contribution < 0} width={110} height={9} />
                      </td>
                      <td className="mono text-2xs num py-1.5 pl-2 w-16"
                          style={{ color: s.contribution > 0 ? 'var(--fusion)' : 'var(--data)' }}>
                        {s.contribution > 0 ? '+' : ''}{s.contribution.toFixed(3)}
                      </td>
                      <td className="text-2xs text-ink-dim py-1.5 pl-3 hidden 2xl:table-cell">
                        {s.meaning}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>

        {/* ================= RIGHT: the picture ============================ */}
        <div className="space-y-3 min-w-0">
          <Panel pad={false}>
            <div className="px-3.5 pt-3">
              <Eyebrow layer="chain">link analysis</Eyebrow>
            </div>
            <GraphView entity={entity} />
          </Panel>

          {d.transactions.length > 0 && (
            <Panel>
              <Eyebrow layer="chain" right={`${d.transactions.length} transactions`}>
                activity timeline
              </Eyebrow>
              <TxTimeline txs={d.transactions} />
            </Panel>
          )}

          <Panel accent={top ? 'network' : undefined}>
            <Eyebrow layer="network" right={a.attribution_status}>network attribution</Eyebrow>
            {d.attribution.length === 0 ? (
              <p className="text-sm text-ink-soft">
                {a.attribution_status === 'suppressed'
                  ? 'Every candidate address is shared infrastructure — a Tor exit, a commercial VPN endpoint, or a host observed announcing for many unrelated entities. Attribution is suppressed rather than reported at a confidence that would mislead.'
                  : a.attribution_status === 'no_significant_link'
                    ? 'No entity-IP association survived FDR control. The observed co-occurrences are consistent with chance given each address’s traffic volume.'
                    : 'No network layer available in this capture; chain-side detection is unaffected.'}
              </p>
            ) : (
              <>
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-rule">
                      {['address', 'asn', 'type', 'obs', 'roots', 'p', 'confidence'].map((h, i) => (
                        <th key={h} className={`eyebrow py-1.5 ${i >= 3 ? 'text-right' : 'text-left'}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {d.attribution.map((c) => (
                      <tr key={c.ip} className="border-b border-rule-soft last:border-0">
                        <td className="mono text-sm py-1.5">{c.ip}</td>
                        <td className="mono text-2xs py-1.5 max-w-[9rem] truncate" title={c.asn_org}>
                          AS{c.asn}
                        </td>
                        <td className="py-1.5"><Tag layer="network">{c.asn_type}</Tag></td>
                        <td className="mono text-2xs num py-1.5">{c.n_observations}</td>
                        <td className="mono text-2xs num py-1.5">{c.root_hits}</td>
                        <td className="mono text-2xs num py-1.5">{c.p_value.toExponential(1)}</td>
                        <td className="num py-1.5">
                          <span className="mono text-md font-semibold">{fmt.conf(c.confidence)}</span>
                          <span className="mono text-2xs text-ink-dim"> ±{fmt.conf(c.interval)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mono text-2xs text-network mt-2 leading-relaxed">
                  Diffusion-adjusted. Bitcoin Core randomises per-peer relay delay, so a single
                  observation is weak evidence by construction; propagation-tree roots are weighted
                  above first-observation, and shared infrastructure is penalised multiplicatively.
                </p>
              </>
            )}
          </Panel>

          {d.behaviour && d.behaviour.diurnality > 0.05 && (
            <Panel>
              <Eyebrow layer="network"
                       right={`fit ${d.behaviour.offset_fit.toFixed(2)} · diurnality ${d.behaviour.diurnality.toFixed(2)}`}>
                behavioural timezone
              </Eyebrow>
              <HourHistogram hist={d.behaviour.hour_histogram}
                             offsetMin={d.behaviour.inferred_offset_min} />
              <p className="text-sm text-ink-soft mt-2">
                Activity is most consistent with an operator in{' '}
                <b className="mono">{fmt.offset(d.behaviour.inferred_offset_min)}</b>.
                Inferred from the shape of the activity histogram alone — independent of the
                GeoIP database, so agreement between the two is real corroboration.
              </p>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
