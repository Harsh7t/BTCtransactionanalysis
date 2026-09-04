/** Live P2P diffusion, drawn on the landing screen.
 *
 * NOT decoration, and specifically not a generic particle field. This is the
 * thing the product is about: a transaction is announced by one peer and spreads
 * across the network with a RANDOMISED per-peer delay - the defence Bitcoin Core
 * added precisely to defeat first-relay inference (Koshy FC'14, Biryukov CCS'14).
 * Every other node lights up later and in an order that carries no reliable
 * information about the origin. That is the problem this tool exists to solve,
 * so it is what the idle screen shows.
 *
 * Canvas rather than SVG: ~44 nodes and ~90 edges repainting at 60fps is a lot
 * of DOM churn for no benefit. Colours are read from the CSS tokens each frame's
 * first paint so the animation follows the theme.
 */
import { useEffect, useRef } from 'react';

type Node = { x: number; y: number; lit: number; origin: boolean };
type Edge = { a: number; b: number; fire: number };

const N_NODES = 44;

export function Propagation({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext('2d');
    if (!ctx) return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0, w = 0, h = 0, dpr = 1;
    let nodes: Node[] = [], edges: Edge[] = [];
    const rand = mulberry(20260826);   // seeded: the same lattice every load

    function layout() {
      const r = cv!.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = r.width; h = r.height;
      cv!.width = Math.round(w * dpr); cv!.height = Math.round(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Jittered grid: a pure random scatter clumps and reads as noise; a pure
      // grid reads as a texture. Bitcoin's topology is neither.
      const cols = 8, rows = Math.max(4, Math.round((cols * h) / Math.max(w, 1)));
      nodes = [];
      for (let i = 0; i < rows; i++) {
        for (let j = 0; j < cols; j++) {
          if (nodes.length >= N_NODES) break;
          nodes.push({
            x: ((j + 0.5) / cols) * w + (rand() - 0.5) * (w / cols) * 0.75,
            y: ((i + 0.5) / rows) * h + (rand() - 0.5) * (h / rows) * 0.75,
            lit: 0, origin: false,
          });
        }
      }
      // Connect each node to its nearest few - a peer keeps a handful of links.
      edges = [];
      nodes.forEach((n, i) => {
        const near = nodes.map((m, k) => ({ k, d: (m.x - n.x) ** 2 + (m.y - n.y) ** 2 }))
          .filter((o) => o.k !== i).sort((a, b) => a.d - b.d).slice(0, 3);
        near.forEach((o) => {
          if (!edges.some((e) => (e.a === o.k && e.b === i) || (e.a === i && e.b === o.k))) {
            edges.push({ a: i, b: o.k, fire: 0 });
          }
        });
      });
    }

    // --- one propagation wave ---------------------------------------------
    let queue: { node: number; at: number }[] = [];
    let seen = new Set<number>();
    let nextWave = 0;

    function announce(t: number) {
      nodes.forEach((n) => { n.lit = 0; n.origin = false; });
      edges.forEach((e) => { e.fire = 0; });
      seen = new Set(); queue = [];
      const origin = Math.floor(rand() * nodes.length);
      nodes[origin].origin = true;
      queue.push({ node: origin, at: t });
      seen.add(origin);
    }

    function step(t: number) {
      // Deliver anything whose randomised delay has elapsed.
      const due = queue.filter((q) => q.at <= t);
      queue = queue.filter((q) => q.at > t);
      due.forEach((q) => {
        nodes[q.node].lit = 1;
        edges.forEach((e) => {
          const other = e.a === q.node ? e.b : e.b === q.node ? e.a : -1;
          if (other < 0 || seen.has(other)) return;
          seen.add(other);
          e.fire = 1;
          // THE POINT: the delay is random per peer, not proportional to
          // distance. Nothing about arrival order names the origin.
          queue.push({ node: other, at: t + 220 + rand() * 900 });
        });
      });
      if (!queue.length && !nextWave) nextWave = t + 1400;
      if (nextWave && t > nextWave) { announce(t); nextWave = 0; }
    }

    function draw(t: number) {
      const cs = getComputedStyle(document.documentElement);
      const tok = (n: string) => cs.getPropertyValue(n).trim();
      // --rule, not --rule-soft: the soft hairline reads fine on paper but on
      // the near-black dark ground the whole lattice disappeared. The mesh has
      // to be equally legible in both themes or the panel is empty in one.
      const rule = tok('--rule') || '#C3CCD4';
      const chain = tok('--chain') || '#2D6A9F';
      const network = tok('--network') || '#7B4B94';
      const dim = tok('--ink-dim') || '#56646F';

      ctx!.clearRect(0, 0, w, h);

      edges.forEach((e) => {
        const A = nodes[e.a], B = nodes[e.b];
        ctx!.beginPath(); ctx!.moveTo(A.x, A.y); ctx!.lineTo(B.x, B.y);
        ctx!.strokeStyle = rule; ctx!.lineWidth = 1;
        ctx!.globalAlpha = 0.7; ctx!.stroke();
        if (e.fire > 0.01) {
          ctx!.strokeStyle = chain; ctx!.lineWidth = 1.4;
          ctx!.globalAlpha = e.fire * 0.9; ctx!.stroke();
          e.fire *= 0.955;
        }
      });
      ctx!.globalAlpha = 1;

      nodes.forEach((n) => {
        const s = n.origin ? 4.5 : n.lit > 0.02 ? 3.4 : 2.2;
        ctx!.beginPath(); ctx!.rect(n.x - s / 2, n.y - s / 2, s, s);
        ctx!.fillStyle = n.origin ? network : n.lit > 0.02 ? chain : dim;
        ctx!.globalAlpha = n.origin ? 1 : n.lit > 0.02 ? 0.4 + n.lit * 0.6 : 0.45;
        ctx!.fill();
        // The origin keeps a ring: the one node we would like to identify, and
        // the one the arrival order will not give us.
        if (n.origin) {
          ctx!.beginPath(); ctx!.arc(n.x, n.y, 9 + Math.sin(t / 420) * 2, 0, Math.PI * 2);
          ctx!.strokeStyle = network; ctx!.globalAlpha = 0.4; ctx!.lineWidth = 1; ctx!.stroke();
        }
        if (n.lit > 0.02) n.lit *= 0.988;
      });
      ctx!.globalAlpha = 1;
    }

    layout();
    if (reduced) {
      // Reduced motion still gets the picture, just not the movement: one
      // fully-propagated frame rather than an empty box.
      announce(0);
      for (let i = 0; i < 400; i++) step(i * 40);
      nodes.forEach((n) => { n.lit = 1; });
      draw(0);
      return;
    }

    announce(performance.now());
    const loop = (t: number) => { step(t); draw(t); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);

    const ro = new ResizeObserver(() => { layout(); announce(performance.now()); });
    ro.observe(cv);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}

/** Small seeded PRNG so the lattice is identical on every load - a layout that
 *  reshuffles on refresh reads as noise rather than as a network. */
function mulberry(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
