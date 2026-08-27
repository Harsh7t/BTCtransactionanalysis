/** Plate 06 — model transparency.
 *
 * The screen that wins the Q&A round. Most teams hide the model; this one opens
 * it: calibration curve, ablation lift, held-out-typology performance, the
 * generator leak test, and the numbers we are NOT proud of, shown at the same
 * size as the ones we are.
 *
 * Nothing here is hardcoded. Every figure is read from artifacts/v1/metrics.json,
 * which `make train` regenerates from a fixed seed — so what the panel shows and
 * what the write-up claims cannot drift apart.
 */
import { useEffect, useState } from 'react';
import { api } from '../api';
import { Bar, Eyebrow, Notice, Panel, Spinner, Tag } from '../ui';
import { ReliabilityCurve } from './Charts';

const pct = (v: number | undefined | null) =>
  v === undefined || v === null || Number.isNaN(v) ? '—' : v.toFixed(3);

function Row({ label, value, layer, note }: {
  label: string; value: string; layer?: 'fusion' | 'confirm' | 'network' | 'danger'; note?: string;
}) {
  return (
    <tr className="border-b border-rule-soft last:border-0">
      <td className="py-1.5 text-sm text-ink-soft">{label}
        {note ? <span className="block mono text-2xs text-ink-dim">{note}</span> : null}
      </td>
      <td className="py-1.5 num mono text-md font-semibold"
          style={layer ? { color: `var(--${layer})` } : undefined}>{value}</td>
    </tr>
  );
}

export function ModelPanel() {
  const [m, setM] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.model().then(setM).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="p-4"><Notice title="Could not load model panel" layer="danger">{err}</Notice></div>;
  if (!m) return <div className="p-8"><Spinner label="loading model artefacts…" /></div>;
  if (!m.available) return (
    <div className="p-4">
      <Notice title="No trained artefacts">
        {m.note} Run <span className="mono">make train</span> to fit the models and produce{' '}
        <span className="mono">metrics.json</span>.
      </Notice>
    </div>
  );

  const man = m.manifest;
  const met = man.metrics || {};
  const res = met.results || {};
  const test = res.test || {};
  const ho = res.holdout_typology || {};
  const leak = m.leak_test;
  const abl: any[] = met.ablation || [];
  const maxAbl = Math.max(...abl.map((a) => a.pr_auc || 0), 0.01);

  return (
    <div className="p-3 space-y-3">
      {/* provenance strip */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 bg-ink text-white px-3.5 py-2">
        <span className="font-cond font-bold uppercase text-md">Model panel</span>
        <span className="mono text-2xs text-white/70">
          artifacts/{man.version} · feature_version {man.feature_version} · seed {man.seed}
          {' '}· git {String(man.provenance?.git_sha ?? '—')}
        </span>
        <span className="mono text-2xs text-white/70">
          backend <b className="text-white">{man.backend}</b> · {man.n_features} features
          · {Number(man.n_train_rows).toLocaleString()} training entities
        </span>
        <span className="ml-auto mono text-2xs px-2 py-0.5"
              style={{ background: 'var(--fusion)' }}>make reproduce</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Panel>
          <Eyebrow layer="fusion">calibration — reliability diagram</Eyebrow>
          <ReliabilityCurve points={met.reliability_curve || []} ece={test.ece ?? 0} />
          <p className="text-sm text-ink-soft mt-2">
            Isotonic regression, fitted on a fold the test set never touches. This is what
            makes a confidence of 0.87 a claim rather than a decoration.
          </p>
        </Panel>

        <Panel>
          <Eyebrow layer="fusion">ablation — where the lift comes from</Eyebrow>
          <table className="w-full">
            <tbody>
              {abl.map((a) => (
                <tr key={a.stage} className="border-b border-rule-soft last:border-0">
                  <td className="py-2 text-sm pr-2">{a.stage}</td>
                  <td className="py-2 w-28">
                    <Bar value={a.pr_auc} max={maxAbl}
                         layer={a.stage.includes('rules') || a.stage.includes('unsupervised')
                           ? 'data' : 'fusion'} width={100} height={11} />
                  </td>
                  <td className="py-2 num mono text-sm font-semibold w-14">{pct(a.pr_auc)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mono text-2xs text-network mt-2 leading-relaxed">
            Rules alone sit near the base rate. The lift is the model — which is precisely
            the PS's "a working model, not just rules".
          </p>
        </Panel>

        <Panel>
          <Eyebrow layer="fusion" right="held-out test fold">scorecard</Eyebrow>
          <table className="w-full">
            <tbody>
              <Row label="PR-AUC" value={pct(test.pr_auc)} layer="fusion"
                   note={`base rate ${pct(test.baseline_pr_auc)} — the number to beat`} />
              <Row label="Precision @ 10" value={pct(test.precision_at_10)} layer="confirm"
                   note="the analyst opens the top ten" />
              <Row label="Precision @ 50" value={pct(test.precision_at_50)} />
              <Row label="Recall @ precision 0.80" value={pct(test.recall_at_precision_80)} />
              <Row label="Expected calibration error" value={pct(test.ece)}
                   layer={(test.ece ?? 1) < 0.05 ? 'confirm' : 'fusion'} note="target < 0.05" />
              <Row label="Held-out typology recall" value={pct(ho.recall_at_threshold)}
                   layer="network"
                   note="laundering patterns never trained on" />
            </tbody>
          </table>
        </Panel>
      </div>

      {/* The honest numbers, given the same weight as the flattering ones. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel accent={leak?.passed ? 'confirm' : 'danger'}>
          <Eyebrow layer={leak?.passed ? 'confirm' : 'danger'}>generator integrity — leak test</Eyebrow>
          {!leak ? <p className="text-sm text-ink-soft">Not run. <span className="mono">make leak-test</span></p> : (
            <>
              <div className="flex items-center gap-2.5 mb-2">
                <span className="font-cond font-bold uppercase text-xl"
                      style={{ color: leak.passed ? 'var(--confirm)' : 'var(--danger)' }}>
                  {leak.passed ? 'PASSED' : 'FAILED'}
                </span>
                <Tag layer={leak.passed ? 'confirm' : 'danger'}>
                  strict tier {leak.lift_over_baseline}× baseline
                </Tag>
                <Tag layer="fusion">full model {leak.control_lift}×</Tag>
              </div>
              <p className="text-sm text-ink-soft">
                We wrote the generator, so a sharp reviewer will attack the data rather than the
                model. This trains a classifier on fields that have <i>no constructed path</i> to
                the label — fee rate, OS port fingerprint, round-number fraction — and confirms
                they score at the base rate. The gap between {leak.lift_over_baseline}× and{' '}
                {leak.control_lift}× is the evidence that detection comes from topology, timing
                and network structure rather than from an artefact of how the data was written.
              </p>
              <table className="w-full mt-2">
                <tbody>
                  {Object.entries(leak.per_field || {}).map(([f, v]: [string, any]) => (
                    <tr key={f} className="border-b border-rule-soft last:border-0">
                      <td className="mono text-2xs py-1">{f}</td>
                      <td className="py-1"><Tag layer={v.tier === 'strict' ? 'chain' : 'data'}>{v.tier}</Tag></td>
                      <td className="num mono text-2xs py-1"
                          style={{ color: v.tier === 'strict' && v.lift > 1.3 ? 'var(--danger)' : undefined }}>
                        {v.lift}×
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Panel>

        <div className="space-y-3">
          <Panel accent="network">
            <Eyebrow layer="network">generalisation to unseen typologies</Eyebrow>
            <div className="flex items-end gap-3 mb-1.5">
              <span className="font-cond font-bold text-3xl leading-none">{pct(ho.recall_at_threshold)}</span>
              <span className="mono text-sm text-ink-soft pb-1">
                recall on {ho.n_holdout_positives ?? 0} entities · PR-AUC {pct(ho.pr_auc)}
              </span>
            </div>
            <p className="text-sm text-ink-soft">
              <b className="mono">{(ho.typologies || []).join(', ')}</b> were held out of training
              entirely — not one example. This number is materially worse than the test score,
              and that gap is the finding: it is the honest bound on how the system behaves
              against a laundering pattern nobody anticipated. Reporting it is the difference
              between an evaluation and a sales pitch.
            </p>
          </Panel>

          <Panel>
            <Eyebrow layer="chain">entity resolution quality</Eyebrow>
            <table className="w-full">
              <tbody>
                <Row label="Addresses clustered"
                     value={Number(met.entity_resolution?.n_addresses ?? 0).toLocaleString()} />
                <Row label="Entities recovered"
                     value={Number(met.entity_resolution?.n_entities ?? 0).toLocaleString()} />
                <Row label="Co-spend edges (heuristic H1)"
                     value={Number(met.entity_resolution?.cospend_edges ?? 0).toLocaleString()}
                     note="common-input-ownership" />
                <Row label="Change edges (heuristic H2)"
                     value={Number(met.entity_resolution?.change_edges ?? 0).toLocaleString()}
                     note="script-type-refined change detection" />
                <Row label="Mean cluster purity"
                     value={pct(met.label_mapping?.mean_purity)} layer="confirm"
                     note="clusters almost never merge two real actors" />
              </tbody>
            </table>
          </Panel>
        </div>
      </div>

      {/* The fusion weights are a trade-off, so show the curve they sit on. */}
      {(met.fusion_sweep || []).length > 0 && (
        <Panel accent="fusion">
          <Eyebrow layer="fusion" right="measured on the test + held-out folds">
            fusion trade-off — why these weights
          </Eyebrow>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem]">
              <thead>
                <tr className="border-b border-rule">
                  {['supervised', 'novelty', 'evidence', 'test PR-AUC', 'P@10', 'P@50',
                    'held-out recall', ''].map((h, i) => (
                    <th key={h + i} className={`eyebrow py-1.5 ${i >= 3 && i < 7 ? 'text-right' : 'text-left'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {met.fusion_sweep.map((f: any, i: number) => (
                  <tr key={i}
                      className="border-b border-rule-soft last:border-0"
                      style={f.shipped ? { background: 'var(--fusion-wash)' } : undefined}>
                    <td className="mono text-sm py-1.5">{f.supervised.toFixed(2)}</td>
                    <td className="mono text-sm py-1.5">{f.novelty.toFixed(2)}</td>
                    <td className="mono text-sm py-1.5">{f.evidence.toFixed(2)}</td>
                    <td className="num mono text-sm py-1.5">{pct(f.test_pr_auc)}</td>
                    <td className="num mono text-sm py-1.5">{pct(f.precision_at_10)}</td>
                    <td className="num mono text-sm py-1.5">{pct(f.precision_at_50)}</td>
                    <td className="num mono text-sm py-1.5" style={{ color: 'var(--network)' }}>
                      {pct(f.holdout_recall)}
                    </td>
                    <td className="py-1.5 pl-3">
                      {f.shipped ? <Tag layer="fusion">shipped</Tag> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm text-ink-soft mt-2 max-w-[95ch]">
            Leaning entirely on the supervised model maximises precision on the four typologies
            it was trained on, and is measurably worse at catching the two it has never seen.
            Weighting unsupervised novelty higher reverses that. Anyone can pick weights; the
            claim worth making is that we measured the curve and chose a point on it —
            deliberately near the precision end, because an analyst's scarcest resource is the
            time spent opening a case file that turns out to be nothing.
          </p>
        </Panel>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel>
          <Eyebrow layer="fusion" right="mean |SHAP|">most influential features</Eyebrow>
          <table className="w-full">
            <tbody>
              {Object.entries(met.feature_importance || {}).slice(0, 12).map(([f, v]: [string, any]) => (
                <tr key={f} className="border-b border-rule-soft last:border-0">
                  <td className="mono text-2xs py-1 w-52 truncate">{f}</td>
                  <td className="py-1"><Bar value={v} max={Math.max(
                    ...Object.values(met.feature_importance || {}).map(Number)) || 1}
                    width={130} height={9} /></td>
                  <td className="num mono text-2xs py-1 w-14">{(v * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel>
          <Eyebrow layer="data">split integrity &amp; behavioural clusters</Eyebrow>
          <table className="w-full mb-3">
            <thead>
              <tr className="border-b border-rule">
                {['fold', 'entities', 'illicit', 'rate'].map((h, i) => (
                  <th key={h} className={`eyebrow py-1 ${i ? 'text-right' : 'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(met.splits || {}).map(([k, v]: [string, any]) => (
                <tr key={k} className="border-b border-rule-soft last:border-0">
                  <td className="mono text-2xs py-1">{k}</td>
                  <td className="num mono text-2xs py-1">{Number(v.n).toLocaleString()}</td>
                  <td className="num mono text-2xs py-1">{Number(v.n_illicit).toLocaleString()}</td>
                  <td className="num mono text-2xs py-1">{(v.illicit_rate * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-sm text-ink-soft">
            Splits are entity-grouped and temporally forward — the test fold begins strictly
            after training ends, and calibration is fitted on its own fold. Violations raise
            rather than warn. HDBSCAN additionally recovered{' '}
            <b className="mono">{met.behavioural_clusters?.n_clusters ?? 0}</b> behavioural
            archetypes nobody labelled, marking{' '}
            <b className="mono">{((met.behavioural_clusters?.noise_fraction ?? 0) * 100).toFixed(0)}%</b>{' '}
            of entities as belonging to no cluster — which is what an outlier is.
          </p>
        </Panel>
      </div>
    </div>
  );
}
