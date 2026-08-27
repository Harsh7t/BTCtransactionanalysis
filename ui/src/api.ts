/** Typed client for the FastAPI surface. One file, no data-fetching library:
 *  every screen loads once and the only polling is the run-progress job. */

export type Alert = {
  run_id: string; rank: number; entity: string; level: string;
  score: number; confidence: number; interval: number;
  novelty: number; supervised: number; evidence_strength: number;
  typologies: string; narrative: string;
  n_addresses: number; n_tx: number; total_out: number; total_in: number;
  n_ips: number; top_asn: number; top_asn_type: string; top_country: string;
  attribution_confidence: number; attribution_status: string;
  verdict: string | null; verdict_reason: string | null;
};

export type Evidence = {
  entity: string; typology: string; strength: number; summary: string;
  txids: string[]; detail: Record<string, unknown>[];
};

export type Counterfactual = { direction: 'up' | 'down'; value: number; text: string };

export type Attribution = {
  entity: string; rank: number; ip: string; asn: number; asn_org: string;
  asn_type: string; country: string; n_observations: number;
  n_entities_on_ip: number; p_value: number; ppmi: number;
  root_hits: number; root_fraction: number; infra_penalty: number;
  timezone_agreement: number; confidence: number; interval: number;
  summary: string; counterfactuals: Counterfactual[]; status: string;
};

export type ShapRow = {
  entity: string; feature: string; contribution: number;
  value: number; direction: string; meaning: string | null;
};

export type Behaviour = {
  entity: string; hour_histogram: number[]; inferred_offset_min: number;
  offset_fit: number; diurnality: number;
};

export type TxRow = {
  entity: string; txid: string; ts: string; value_out: number; fee: number;
  n_inputs: number; n_outputs: number; output_entropy: number;
  peel_ratio: number | null; tx_score: number;
};

export type CaseFile = {
  run_id: string; alert: Alert; evidence: Evidence[]; attribution: Attribution[];
  shap: ShapRow[]; behaviour: Behaviour | null; transactions: TxRow[];
};

export type Receipt = {
  file: string; format: string; rows_read: number; rows_clean: number;
  rows_quarantined: number; duplicates_removed: number;
  quarantine_breakdown: Record<string, number>;
  unmapped_input_columns: string[]; chain_only_mode: boolean;
  n_entities_resolved: number; n_entities_active: number;
  n_transactions: number; n_graph_edges: number;
  duration_s: number; rows_per_second: number; n_alerts: number;
  threshold: number; n_below_threshold: number; degraded_no_model: boolean;
  enrichment: Record<string, unknown>; attribution: Record<string, unknown>;
  embeddings: Record<string, unknown>; timings: Record<string, number>;
  resolve_n_entities?: number; resolve_change_edges?: number;
  resolve_cospend_edges?: number;
};

export type Run = {
  run_id: string; created_at: string; source_file: string;
  n_rows: number; n_entities: number; n_alerts: number; duration_s: number;
  receipt: Receipt; timings: Record<string, number>;
  provenance: Record<string, unknown>; metrics: Record<string, unknown>;
};

export type Job = {
  job_id: string; state: 'running' | 'done' | 'error'; stage?: string;
  file: string; run_id?: string; receipt?: Receipt; error?: string;
};

export type GraphData = {
  nodes: { id: string; subject: boolean; alerted: boolean }[];
  edges: { src: string; dst: string; value: number; n_tx: number }[];
  meta: { nodes_shown: number; hops: number; capped?: boolean };
};

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${url}`);
  return r.json() as Promise<T>;
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${url}`);
  return r.json() as Promise<T>;
}

export const api = {
  health: () => get<{ status: string; model_artifacts: boolean; backend: string | null; threshold: number }>('/api/health'),
  latestRun: () => get<{ run: Run | null }>('/api/runs/latest'),
  runs: () => get<{ runs: Run[] }>('/api/runs'),
  samples: () => get<{ samples: { name: string; path: string; mb: number }[] }>('/api/samples'),
  startRun: (path?: string) => post<{ job_id: string }>('/api/runs', { path }),
  job: (id: string) => get<Job>(`/api/jobs/${id}`),

  alerts: (q: Record<string, string | number | boolean | undefined>) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => {
      if (v !== undefined && v !== '' && v !== false) p.set(k, String(v));
    });
    return get<{ run_id: string; alerts: Alert[]; sweep: { bucket: number; n: number }[] }>(
      `/api/alerts?${p}`);
  },
  caseFile: (entity: string) => get<CaseFile>(`/api/alerts/${encodeURIComponent(entity)}`),
  graph: (entity: string, hops = 2) =>
    get<GraphData>(`/api/graph/${encodeURIComponent(entity)}?hops=${hops}`),
  verdict: (entity: string, verdict: string, reason = '') =>
    post<{ ok: boolean }>(`/api/alerts/${encodeURIComponent(entity)}/verdict`,
      { verdict, reason }),
  transactions: (minScore = 0, limit = 200) =>
    get<{ run_id: string; transactions: TxRow[] }>(
      `/api/transactions?min_score=${minScore}&limit=${limit}`),
  expand: (entity: string) => get<{
    entity: string; addresses: { address: string }[];
    transactions: { txid: string; ts: string; value: number }[];
    truncated: boolean; n_addresses_total: number;
  }>(`/api/graph/${encodeURIComponent(entity)}/expand`),
  model: () => get<{ available: boolean; manifest?: any; leak_test?: any;
                     sensitivity?: any; external?: any; note?: string }>('/api/model'),
  provenance: () => get<any>('/api/provenance'),

  upload: async (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(`upload failed: ${r.status}`);
    return r.json() as Promise<{ job_id: string; file: string; bytes: number }>;
  },
  exportUrl: (entity: string) => `/api/alerts/${encodeURIComponent(entity)}/export`,
};

// ---------------------------------------------------------------- formatting
export const fmt = {
  int: (n: number | null | undefined) => (n ?? 0).toLocaleString('en-US'),
  btc: (sats: number | null | undefined) => ((sats ?? 0) / 1e8).toFixed(4),
  pct: (n: number) => `${(n * 100).toFixed(0)}%`,
  conf: (n: number | null | undefined) => (n ?? 0).toFixed(2),
  /** Typology slugs are snake_case in the store; analysts read prose. */
  typology: (t: string) => t.replace(/_/g, ' '),
  offset: (min: number) => {
    const s = min < 0 ? '-' : '+';
    const m = Math.abs(min);
    return `UTC${s}${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  },
  time: (iso: string) => (iso || '').replace('T', ' ').replace(/\.\d+/, '').replace('Z', ''),
  bytes: (b: number) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e3).toFixed(0)} KB`),
};
