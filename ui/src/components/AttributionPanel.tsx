/** The attribution panel — the part nobody else builds.
 *
 *  Every commercial chain-analysis product treats src_ip as a column. This runs
 *  inference in the other direction: given this on-chain entity, which network
 *  identity is behind it, and how sure are we?
 *
 *  Three things must always be visible, because leaving any of them out is how
 *  an attribution claim becomes an overclaim:
 *    - the CONFIDENCE INTERVAL, which widens when evidence is thin
 *    - the DISCOUNT and its reason (shared host, Tor exit, few sightings)
 *    - SUPPRESSION, stated plainly, when no honest claim can be made
 *
 *  A panel that always produces an answer is not an attribution engine.
 */
import type { Alert, Attribution, Behaviour } from '../api';
import { fmt } from '../api';
import { Card, ConfBar, Pill, Section } from './ui';

const INFRA_LAYER = (t: string) =>
  t === 'residential' || t === 'mobile' ? 'confirm'
    : t === 'hosting' ? 'chain' : 'network';

export function AttributionPanel({ attribution, alert, behaviour }: {
  attribution: Attribution[]; alert: Alert; behaviour: Behaviour | null;
}) {
  const status = alert.attribution_status;

  if (!attribution.length || status === 'no_network_layer' || status === 'no_significant_link') {
    return (
      <Section title="Network attribution" layer="network">
        <Card layer="network" className="px-3 py-2.5">
          <div className="text-fg-muted">
            {status === 'no_network_layer'
              ? 'This capture carries no usable IP column, so the system is running in chain-only mode. Detection is unaffected; attribution is simply not available.'
              : 'No entity-to-IP association survived false-discovery control. The co-occurrences we observed are consistent with chance given how much traffic each address carries.'}
          </div>
          <div className="text-2xs text-fg-dim mt-1.5">
            Reporting nothing is the correct output here. An engine that always
            names an address is guessing.
          </div>
        </Card>
      </Section>
    );
  }

  const suppressed = status === 'suppressed';

  return (
    <Section title="Network attribution" layer="network"
      right={<span className="mono text-2xs text-network">
        diffusion-adjusted · {attribution.length} candidate{attribution.length > 1 ? 's' : ''}
      </span>}>

      {suppressed && (
        <Card layer="danger" className="px-3 py-2 mb-2">
          <div className="text-danger text-xs font-semibold mb-0.5">Attribution suppressed</div>
          <div className="text-fg-muted text-2xs">
            Every candidate address is shared infrastructure. Reporting a number here
            would mislead, so the claim is withheld rather than degraded — the candidates
            below are shown for transparency, not as an identification.
          </div>
        </Card>
      )}

      <div className="space-y-1.5">
        {attribution.map((c) => (
          <Card key={c.ip} className="px-3 py-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-1.5">
              <span className="mono text-md font-semibold">{c.ip}</span>
              <Pill layer={INFRA_LAYER(c.asn_type)}>{c.asn_type}</Pill>
              <span className="mono text-2xs text-fg-dim">
                AS{c.asn} · {c.asn_org} · {c.country}
              </span>
              <div className="ml-auto">
                <ConfBar value={c.confidence} interval={c.interval} layer="network" width={90} />
              </div>
            </div>

            {/* The arithmetic behind the number, so it can be checked rather than trusted. */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-1 mono text-2xs">
              <Metric label="sightings" v={String(c.n_observations)}
                hint="repeat observation is what survives randomised relay delay" />
              <Metric label="tree roots" v={`${c.root_hits} (${fmt.pct(c.root_fraction)})`}
                hint="propagation-tree roots outrank first-observation evidence" />
              <Metric label="p-value" v={c.p_value < 1e-4 ? c.p_value.toExponential(1) : c.p_value.toFixed(4)}
                hint="hypergeometric, vs a null that accounts for this address's traffic volume" />
              <Metric label="discount" v={`×${c.infra_penalty.toFixed(2)}`}
                hint="shared-infrastructure penalty" layer={c.infra_penalty < 0.5 ? 'danger' : undefined} />
            </div>

            {c.n_entities_on_ip > 1 && (
              <div className="text-2xs text-network mt-1">
                observed announcing for {c.n_entities_on_ip} distinct entities — shared host
              </div>
            )}

            {c.counterfactuals?.length > 0 && (
              <div className="mt-1.5 pt-1.5 border-t border-border space-y-0.5">
                {c.counterfactuals.slice(0, 2).map((cf, i) => (
                  <div key={i} className="text-2xs flex gap-1.5 items-baseline">
                    <span className={cf.direction === 'down' ? 'text-danger' : 'text-confirm'}>
                      {cf.direction === 'down' ? '↓' : '↑'}
                    </span>
                    <span className="text-fg-dim">{cf.text}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>

      {behaviour && behaviour.diurnality > 0.15 && (
        <Card className="px-3 py-2 mt-2">
          <div className="eyebrow text-network mb-1">Behavioural timezone</div>
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="mono text-md text-fg">
              {fmt.offset(behaviour.inferred_offset_min)}
            </span>
            <span className="text-2xs text-fg-dim">
              inferred from activity hours alone · fit {behaviour.offset_fit.toFixed(2)} ·
              diurnality {behaviour.diurnality.toFixed(2)}
            </span>
          </div>
          <p className="text-2xs text-fg-dim mt-1">
            Derived from when this entity transacts, independently of the GeoIP database.
            Where the two agree, two unrelated methods have converged and confidence rises;
            where they disagree, something is being routed through somewhere it isn't.
          </p>
        </Card>
      )}

      <p className="text-2xs text-fg-dim mt-2 leading-relaxed">
        Bitcoin Core relays transactions with a randomised per-peer delay, specifically to
        frustrate origin inference from first-relay observations. This engine models that
        defence: single sightings are down-weighted, propagation-tree roots are weighted
        above them, and shared infrastructure is penalised. The numbers above are lower than
        a naive first-relay method would report — deliberately.
      </p>
    </Section>
  );
}

function Metric({ label, v, hint, layer }: {
  label: string; v: string; hint?: string; layer?: 'danger';
}) {
  return (
    <div title={hint}>
      <span className="text-fg-dim/70">{label} </span>
      <span className={layer === 'danger' ? 'text-danger' : 'text-fg-muted'}>{v}</span>
    </div>
  );
}
