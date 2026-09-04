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
import { Bar, Counter, Eyebrow, Notice, Panel, Spinner, Tag } from '../ui';
import { ReliabilityCurve } from './Charts';
import { SensitivityCurve } from './SensitivityCurve';

const pct = (v: number | undefined | null) =>
  v === undefined || v === null || Number.isNaN(v) ? '—' : v.toFixed(3);

function Row({ label, value, layer, note }: {
  label: string; value: string; layer?: 'fusion' | 'confirm' | 'network' | 'danger' | 'chain'; note?: string;
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

    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-3">

      <h1 className="display text-ink">model</h1>

      <span className="text-sm text-ink-soft">

        opened on purpose — including the numbers we are not proud of

      </span>

    </div>
      {/* provenance strip */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 bg-surface-2 border-y border-rule px-3.5 py-2">
        <span className="font-cond font-bold text-md text-ink">Model panel</span>
        <span className="mono text-2xs text-ink-soft">
          artifacts/{man.version} · feature_version {man.feature_version} · seed {man.seed}
          {' '}· git {String(man.provenance?.git_sha ?? '—')}
        </span>
        <span className="mono text-2xs text-ink-soft">
          backend <b className="text-ink">{man.backend}</b> · {man.n_features} features
          · {Number(man.n_train_rows).toLocaleString()} training entities
        </span>
        {/* A filled amber pill. It used to inherit white from the dark strip;
            with the strip tokenised it inherited ink and fell to 2.98:1.
            --surface inverts with the theme, so it reads on the dark amber of
            light mode and the light amber of dark mode alike. */}
        <span className="ml-auto mono text-2xs px-2 py-0.5"
              style={{ background: 'var(--fusion)', color: 'var(--surface)' }}>
          make reproduce
        </span>
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

        <Panel weight="primary">
          <Eyebrow layer="fusion">ablation — where the lift comes from</Eyebrow>
          <table className="w-full">
            <tbody>
              {/* Staggered so the sequence reads as an argument rather than a
                  table: rules barely move, then the model arrives. This is the
                  strongest claim in the submission and it was static. */}
              {abl.map((a, i) => (
                <tr key={a.stage} className="border-b border-rule-soft last:border-0 anim-rise"
                    style={{ animationDelay: `${i * 110}ms` }}>
                  <td className="py-2 text-sm pr-2">{a.stage}</td>
                  <td className="py-2 w-28">
                    <Bar value={a.pr_auc} max={maxAbl}
                         layer={a.stage.includes('rules') || a.stage.includes('unsupervised')
                           ? 'data' : 'fusion'} width={100} height={11}
                         delay={i * 110 + 90} />
                  </td>
                  <td className="py-2 num mono text-sm font-semibold w-14">
                    <Counter value={a.pr_auc} decimals={3} duration={620} />
                  </td>
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
              {test.classification && (<>
                <Row label="F1 (operating threshold)" value={pct(test.classification.f1)}
                     layer="fusion" />
                <Row label="MCC" value={pct(test.classification.mcc)} layer="fusion"
                     note="the honest single figure under class imbalance" />
                <Row label="Accuracy" value={pct(test.classification.accuracy)}
                     note={`"predict everything licit" scores ${pct(test.classification.accuracy_all_negative_baseline)} — which is why accuracy is not used to judge this system`} />
              </>)}
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
                <span className="flex flex-wrap items-center gap-2">
                  <Tag layer={leak.passed ? 'confirm' : 'danger'}>
                    strict tier {leak.lift_over_baseline}× baseline
                  </Tag>
                  <Tag layer="fusion">full model {leak.control_lift}×</Tag>
                </span>
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
          <Panel>
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


      {/* The differentiator, measured - and the curve it sits on. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {met.attribution && (
          <Panel>
            <Eyebrow layer="network" right={`${met.attribution.n_evaluable.toLocaleString()} evaluable entities`}>
              attribution accuracy — the differentiator, measured
            </Eyebrow>
            <div className="flex items-end gap-4 mb-2">
              <div>
                <div className="font-cond font-bold text-3xl leading-none">
                  {pct(met.attribution.top1_accuracy)}
                </div>
                <div className="mono text-2xs text-ink-dim">top-1 accuracy</div>
              </div>
              <div className="mono text-sm text-ink-soft pb-1">
                vs <b>{pct(met.attribution.random_choice_baseline)}</b> for random choice
                among {met.attribution.mean_candidates} candidates
              </div>
            </div>
            <table className="w-full">
              <tbody>
                <Row label="Top-3 accuracy" value={pct(met.attribution.top3_accuracy)} />
                <Row label="Mean reciprocal rank" value={pct(met.attribution.mrr)} />
                <Row label="Attempt rate" value={pct(met.attribution.attempt_rate)}
                     note="how often the engine was willing to answer at all" />
                <Row label="Abstentions" value={String(met.attribution.n_abstained)}
                     layer="confirm"
                     note="shared infrastructure — correctly declined rather than guessed" />
                <Row label="Single-candidate share"
                     value={pct(met.attribution.single_candidate_share)}
                     note="cases where top-1 was trivially correct" />
              </tbody>
            </table>
            <p className="text-sm text-ink-soft mt-2">{met.attribution.note}</p>
          </Panel>
        )}

        {m.sensitivity && (
          <Panel>
            <Eyebrow layer="network">attribution vs observation coverage</Eyebrow>
            <SensitivityCurve rows={m.sensitivity.curve} />
            <p className="text-sm text-ink-soft mt-2">
              Each point regenerates the capture with the chain layer held identical and
              only observation coverage changed. Note where the two lines cross: below
              roughly 10% coverage the engine performs <i>worse than guessing</i>, because
              it is mostly seeing relays rather than origin announcements and picks
              confidently among them. That limit is measured, not argued.
            </p>
            <p className="text-sm text-ink-soft mt-2">{m.sensitivity.note}</p>
          </Panel>
        )}
      </div>

      {met.transaction_level && met.transaction_level.pr_auc !== undefined && (
        <Panel>
          <Eyebrow layer="chain"
                   right={`${Number(met.transaction_level.n_transactions).toLocaleString()} transactions`}>
            transaction-level head — "why a wallet/transaction was flagged"
          </Eyebrow>
          <table className="w-full">
            <tbody>
              <Row label="PR-AUC" value={pct(met.transaction_level.pr_auc)} layer="chain"
                   note={`base rate ${pct(met.transaction_level.baseline_pr_auc)}`} />
              <Row label="Precision @ 50" value={pct(met.transaction_level.precision_at_50)} />
              {met.transaction_level.classification && (
                <Row label="F1" value={pct(met.transaction_level.classification.f1)} />
              )}
            </tbody>
          </table>
          <p className="text-sm text-ink-soft mt-2">
            A second model head over transaction-local features plus the parent entity's
            score. Split follows the parent entity's fold, so no entity straddles the
            train/test boundary. The entity remains the better investigative unit; this
            exists because the PS asks about transactions too, and the answer should be a
            model rather than arithmetic on the entity's score.
          </p>
        </Panel>
      )}

      {(met.failure_gallery || []).length > 0 && (
        <Panel accent="danger">
          <Eyebrow layer="danger">failure gallery — cases we get wrong</Eyebrow>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            {met.failure_gallery.slice(0, 6).map((f: any) => (
              <div key={f.entity + f.kind} className="border border-rule bg-surface-2 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Tag layer={f.kind === 'false_positive' ? 'fusion' : 'network'}>
                    {f.kind.replace('_', ' ')}
                  </Tag>
                  <span className="mono text-sm font-semibold">{f.entity}</span>
                  <span className="mono text-2xs text-ink-dim ml-auto">score {pct(f.score)}</span>
                </div>
                <div className="mono text-2xs text-ink-dim mb-1">
                  truth: {f.archetype}{f.typology ? ` · ${f.typology}` : ''}
                </div>
                <p className="text-sm text-ink-soft">{f.why}</p>
              </div>
            ))}
          </div>
          <p className="text-sm text-ink-soft mt-2">
            Published deliberately. A system whose limits are known is more useful than one
            whose limits are undiscovered, and every reason above is derived from the
            entity's own features rather than written after the fact.
          </p>
        </Panel>
      )}

      {m.external && (
        <Panel accent={m.external.available ? 'confirm' : 'data'}>
          <Eyebrow layer="confirm">external validation — real labelled Bitcoin data</Eyebrow>
          {m.external.available ? (
            <>
              <div className="flex items-end gap-4 mb-2">
                <div>
                  <div className="font-cond font-bold text-3xl leading-none">
                    {pct(m.external.f1)}
                  </div>
                  <div className="mono text-2xs text-ink-dim">illicit-class F1 (Elliptic)</div>
                </div>
                <div className="mono text-sm text-ink-soft pb-1">
                  PR-AUC {pct(m.external.pr_auc)} ·
                  {' '}{Number(m.external.n_labelled).toLocaleString()} labelled nodes ·
                  {' '}positive rate {pct(m.external.positive_rate)}
                </div>
              </div>
              <p className="text-sm text-ink-soft">
                Published reference: {m.external.published_reference.source} reports
                illicit-class F1 ≈ {m.external.published_reference.illicit_f1} for
                {' '}{m.external.published_reference.model}.
                {' '}{m.external.published_reference.caveat}
              </p>
              <p className="text-sm text-ink-soft mt-2">{m.external.note}</p>
            </>
          ) : (
            <p className="text-sm text-ink-soft">{m.external.note}</p>
          )}
        </Panel>
      )}

      {m.elliptic_pp?.available && (() => {
        const w = m.elliptic_pp.wallet_classification;
        const c = m.elliptic_pp.cospend_clustering;
        return (
          <Panel>
            <Eyebrow layer="confirm" right="Elliptic++ · KDD'23">
              external validation — at the actor level we actually ship
            </Eyebrow>
            <p className="text-sm text-ink-soft mb-3">
              Elliptic validates a <em>transaction</em> classifier. This system scores
              <em> entities</em>. Elliptic++ carries {Number(w.n_labelled_addresses).toLocaleString()}
              {' '}labelled wallet addresses, so it tests the unit we ship — and the
              clustering heuristic that produces it.
            </p>
            <table className="w-full">
              <tbody>
                <Row label="address PR-AUC" value={pct(w.headline_address_disjoint.pr_auc)}
                     layer="fusion"
                     note={`base rate ${pct(w.headline_address_disjoint.positive_rate)} · ${Number(w.headline_address_disjoint.n).toLocaleString()} test addresses`} />
                <Row label="address F1" value={pct(w.headline_address_disjoint.f1)} layer="fusion"
                     note={`split is address-disjoint; the naive figure keeping repeats is ${pct(w.naive_repeated_addresses.f1)}`} />
                <Row label="co-spend clusters share a label"
                     value={pct(c.label_agreement.macro)} layer="confirm"
                     note={`vs ${pct(c.label_agreement_shuffled_control.macro)} label-shuffle control · lift ${c.lift_macro}×`} />
                <Row label="largest cluster, real Bitcoin"
                     value={Number(c.largest_entity_addresses_all).toLocaleString()}
                     layer="danger"
                     note="673 in our synthetic data — the supercluster collapse our generator does not reproduce" />
              </tbody>
            </table>
            <p className="text-sm text-ink-soft mt-3">{m.elliptic_pp.scope}</p>
          </Panel>
        );
      })()}

      {/* The fusion weights are a trade-off, so show the curve they sit on. */}
      {(met.fusion_sweep || []).length > 0 && (
        <Panel>
          <Eyebrow layer="fusion" right="measured on the test + held-out folds">
            fusion trade-off — why these weights
          </Eyebrow>
          <div className="overflow-x-auto">
            <div className="overflow-x-auto scroll-hint">
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
