/** k-hop link analysis.
 *
 * Cytoscape rather than a hand-rolled force layout: it does incremental layout,
 * pan/zoom, and hit-testing properly, and this is the one view where those are
 * genuinely hard. The subgraph arrives already extracted and node-capped by the
 * server — sending an unbounded neighbourhood to the browser is exactly how
 * link-analysis views die (roadmap §4.4 R4).
 *
 * The node cap is stated in the UI rather than hidden. "Showing 214 of 12,847"
 * is information; silently truncating is a lie of omission.
 */
import { useEffect, useRef, useState } from 'react';
import cytoscape, { type Core } from 'cytoscape';
import { api, fmt, type GraphData } from '../api';
import { Button, Spinner } from '../ui';

export function GraphView({ entity }: { entity: string }) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const [data, setData] = useState<GraphData | null>(null);
  const [hops, setHops] = useState(2);
  const [sel, setSel] = useState<string | null>(null);
  // The PS names IPs, WALLETS and transactions. Entity supernodes are the right
  // default; the address and transaction layers beneath are one click away.
  const [expanded, setExpanded] = useState(false);
  const [sub, setSub] = useState<{
    addresses: { address: string }[];
    transactions: { txid: string; ts: string; value: number }[];
    truncated: boolean; n_addresses_total: number;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    api.graph(entity, hops)
      .then((g) => live && setData(g))
      .catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, [entity, hops]);

  useEffect(() => {
    if (!expanded) { setSub(null); return; }
    let live = true;
    api.expand(entity).then((r) => live && setSub(r)).catch(() => {});
    return () => { live = false; };
  }, [expanded, entity]);

  useEffect(() => {
    if (!data || !box.current) return;
    cy.current?.destroy();

    const elements = [
      ...(sub ? sub.addresses.map((a) => ({
        data: { id: a.address, kind: 'address', label: '' },
      })) : []),
      ...(sub ? sub.transactions.map((t) => ({
        data: { id: t.txid, kind: 'tx', label: '' },
      })) : []),
      ...(sub ? sub.addresses.flatMap((a) =>
        sub.transactions.slice(0, 20).map((t, j) => ({
          data: { id: `w${a.address}-${j}`, source: a.address, target: t.txid },
        }))).slice(0, 300) : []),
      ...data.nodes.map((n) => ({
        data: { id: n.id, subject: n.subject, alerted: n.alerted,
                label: n.subject ? n.id : n.id.replace(/^ENT-/, '') },
      })),
      ...data.edges.map((e, i) => ({
        data: { id: `e${i}`, source: e.src, target: e.dst, value: e.value, n_tx: e.n_tx },
      })),
    ];

    const inst = cytoscape({
      container: box.current,
      elements,
      // Square-ish, flat, no glow — the same restraint as the rest of the app.
      style: [
        { selector: 'node', style: {
          'background-color': '#AEB9C3', width: 9, height: 9,
          label: '', 'border-width': 0,
        } },
        { selector: 'node[?alerted]', style: {
          'background-color': '#B8791C', width: 13, height: 13,
        } },
        { selector: 'node[?subject]', style: {
          'background-color': '#0E1C27', width: 20, height: 20,
          label: 'data(label)', 'font-family': 'Spline Sans Mono', 'font-size': 9,
          'text-valign': 'bottom', 'text-margin-y': 5, color: '#0E1C27',
        } },
        { selector: 'edge', style: {
          width: 1, 'line-color': '#C3CCD4', 'curve-style': 'straight',
          'target-arrow-shape': 'triangle', 'target-arrow-color': '#C3CCD4',
          'arrow-scale': 0.5,
        } },
        { selector: 'edge[value > 100000000]', style: { width: 2, 'line-color': '#7B4B94' } },
        // Wallet and transaction nodes are shaped differently, not just tinted,
        // so the three layers stay distinguishable without relying on colour.
        { selector: 'node[kind = "address"]', style: {
          'background-color': '#2D6A9F', width: 7, height: 7, shape: 'rectangle',
        } },
        { selector: 'node[kind = "tx"]', style: {
          'background-color': '#5C6B78', width: 6, height: 6, shape: 'diamond',
        } },
        { selector: '.hi', style: {
          'line-color': '#B8791C', 'target-arrow-color': '#B8791C', width: 2.5, 'z-index': 9,
        } },
        { selector: 'node:selected', style: {
          'border-width': 2, 'border-color': '#2D6A9F',
        } },
      ],
      layout: {
        name: 'cose', animate: false, nodeRepulsion: 9000,
        idealEdgeLength: 55, padding: 24, randomize: false,
      } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.25,
      minZoom: 0.15, maxZoom: 3,
    });

    // Highlight the subject's immediate flows: the money path, not decoration.
    inst.$(`#${CSS.escape(entity)}`).connectedEdges().addClass('hi');
    inst.on('tap', 'node', (evt) => setSel(evt.target.id()));
    inst.on('tap', (evt) => { if (evt.target === inst) setSel(null); });

    cy.current = inst;
    return () => { inst.destroy(); cy.current = null; };
  }, [data, entity, sub]);

  if (err) return <div className="p-3.5 text-sm text-danger">{err}</div>;

  return (
    <div>
      <div className="flex items-center gap-2 px-3.5 pb-2">
        <span className="mono text-2xs text-ink-dim">
          {data ? <>showing <b className="text-ink">{fmt.int(data.meta.nodes_shown)}</b> nodes
            · {fmt.int(data.edges.length)} edges · {data.meta.hops} hop{data.meta.hops > 1 ? 's' : ''}
            {data.meta.capped ? <span className="text-fusion"> · capped</span> : null}
            {sub ? <span className="text-chain"> · {sub.addresses.length} of {sub.n_addresses_total} wallets
              · {sub.transactions.length} transactions</span> : null}</>
            : 'extracting subgraph…'}
        </span>
        <div className="ml-auto flex items-center gap-1.5 no-print">
          {[1, 2, 3].map((h) => (
            <button key={h} onClick={() => setHops(h)} aria-pressed={hops === h}
                    className="mono text-2xs w-7 h-6 border transition-colors duration-150 cursor-pointer"
                    style={hops === h
                      ? { borderColor: 'var(--chain)', color: 'var(--chain)', background: 'var(--chain-wash)' }
                      : { borderColor: 'var(--rule)', color: 'var(--ink-soft)' }}>
              {h}h
            </button>
          ))}
          <Button variant={expanded ? 'default' : 'ghost'}
                  onClick={() => setExpanded(!expanded)}
                  title="Show the constituent wallets and transactions of this entity">
            {expanded ? 'collapse wallets' : 'expand wallets'}
          </Button>
          <Button variant="ghost" onClick={() => cy.current?.fit(undefined, 24)}>fit</Button>
        </div>
      </div>

      <div className="relative border-t border-rule bg-[#FAFBFC]" style={{ height: 330 }}>
        {!data && (
          <div className="absolute inset-0 grid place-items-center">
            <Spinner label="laying out graph…" />
          </div>
        )}
        <div ref={box} className="w-full h-full" />
        {sel && (
          <div className="absolute bottom-2 left-2 bg-surface border border-rule px-2.5 py-1.5">
            <span className="mono text-2xs text-ink-dim">selected </span>
            <span className="mono text-sm font-semibold">{sel}</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 px-3.5 py-2 border-t border-rule bg-surface-2">
        {[['#0E1C27', 'subject'], ['#B8791C', 'alerted entity'],
          ['#AEB9C3', 'neighbourhood'], ['#7B4B94', 'high-value edge'],
          ...(sub ? [['#2D6A9F', 'wallet (address)'], ['#5C6B78', 'transaction']] : []),
        ].map(([c, l]) => (
          <span key={l} className="mono text-2xs text-ink-soft flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 inline-block" style={{ background: c }} />{l}
          </span>
        ))}
      </div>
    </div>
  );
}
