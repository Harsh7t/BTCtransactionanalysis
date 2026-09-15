/** The nine pipeline stages, and what each one actually does.
 *
 * Lives here rather than in Processing.tsx because the landing page's
 * "how it works" section teaches the same nine stages before a run exists.
 * One copy: the wait screen and the explainer can never drift apart.
 */
export const STAGES: [string, string][] = [
  ['ingest', 'parse CSV / JSONL / XML, quarantine bad rows'],
  ['enrich', 'resolve every IP to ASN and country, offline'],
  ['resolve', 'collapse addresses into actors — common-input ownership'],
  ['graph', 'actor-to-actor money flow, entity × IP matrix'],
  ['features', '141 features per actor, including Node2Vec'],
  ['detect', 'score every actor, calibrate the probability'],
  ['attribute', 'which IP is really theirs — with FDR control'],
  ['explain', 'exact SHAP, turned into English'],
  ['store', 'write the case files'],
];

/* What each stage is actually doing, at the size someone will read it.
 *
 * A hundred seconds of waiting is the longest uninterrupted attention this
 * interface ever gets. Spending it on a spinner wastes the best teaching moment
 * in the demo, so the panel below the track explains the running stage - and
 * these are the real mechanisms, not progress-bar filler. */
export const DETAIL: [string, string][] = [
  ['Reading the capture',
   'CSV, JSONL and XML all parse to one internal frame, and all three are verified to ' +
   'produce identical clean-row counts. Rows that fail validation are quarantined with a ' +
   'named reason and counted in the receipt — never silently dropped, because an analyst ' +
   'has to know what was excluded before trusting what was kept.'],
  ['Locating every peer',
   'Each IP resolves to an ASN, a country and an infrastructure class from a DB-IP Lite ' +
   'database bundled inside the image. No lookup leaves this machine. Infrastructure class ' +
   'matters later: it is what decides whether an attribution is trustworthy or suppressed.'],
  ['Addresses become actors',
   'Bitcoin has addresses, not people. But if one transaction spends from five addresses at ' +
   'once, whoever signed it held all five private keys — so those addresses are one actor. ' +
   'Chain those merges and 1.8 million addresses collapse into roughly 830,000 actors. ' +
   'Verified on real Bitcoin: addresses this groups share a label 99.79% of the time.'],
  ['Drawing the money',
   'Actor-to-actor flow, PageRank and sampled betweenness, plus the sparse entity × IP ' +
   'co-occurrence matrix the attribution test needs. Sparse, not dense — that is what keeps ' +
   '2.4 million rows inside laptop memory.'],
  ['Describing each actor',
   '141 numbers per actor: chain behaviour, timing rhythm, network posture, position in the ' +
   'money graph, and 64 learned Node2Vec dimensions. The most expensive stage by far, and ' +
   'fully vectorised — it is expressed as Polars expressions so the whole matrix computes in ' +
   'parallel rather than row by row.'],
  ['Scoring every actor',
   'Gradient-boosted trees score all of them, then isotonic regression calibrates the output ' +
   'so that 0.90 means roughly a 90% chance rather than merely "higher than 0.80". Measured ' +
   'calibration error on the bulk profile: 0.0381.'],
  ['Who was it?',
   'For every actor–IP pair, a hypergeometric test asks whether they co-occur more than ' +
   'chance predicts given how much traffic each generates — with Benjamini–Hochberg control ' +
   'across all pairs at α = 0.01. Where the evidence points at shared infrastructure the ' +
   'attribution is suppressed rather than guessed. On the bulk run, 28,661 were suppressed.'],
  ['Why it was flagged',
   'Exact SHAP values — TreeExplainer, not an approximation — for the alerts actually shown. ' +
   'Sixty of them, not 830,000: there is no reason to explain alerts nobody will open. The ' +
   'top contributions become an English narrative an analyst can act on.'],
  ['Writing the case files',
   'Alerts, evidence chains with real TXIDs, attributions, SHAP rows and the run provenance ' +
   'all go to DuckDB — the input SHA-256, the seed, the feature version, the model backend ' +
   'and the git commit, so every figure traces back to an exact input and an exact model.'],
];

/* The same nine stages in plain English, for the landing page.
 *
 * DETAIL above is written for someone who already knows what a hypergeometric
 * test is; this is written for the first thirty seconds, before anyone has
 * agreed to care. Both are true and both describe the same code - the landing
 * shows the plain line first and the technical one under it, so nobody has to
 * choose which audience the page is for. */
export const PLAIN: string[] = [
  'Read the file. Anything malformed is set aside and counted — never quietly dropped, ' +
  'because you have to know what was excluded before you can trust what was kept.',

  'Work out which network each IP address belongs to, using a database that ships inside ' +
  'the image. Nothing is looked up over the internet, because there is no internet.',

  'Bitcoin has addresses, not people. If one payment spends from five addresses at once, ' +
  'one person held all five keys — so those five are one owner. Repeat until nothing merges.',

  'Draw who paid whom, and separately, which owners were seen coming from which IP addresses. ' +
  'Both are needed: one is the money, the other is the machine.',

  'Describe every owner with 141 numbers — how they spend, what hours they keep, who they ' +
  'deal with, where they sit in the flow of money.',

  'Score every owner for how unusual they look, then convert that score into an honest ' +
  'probability, so 0.90 means about a nine-in-ten chance rather than just "more than 0.80".',

  'Ask whether an owner and an IP genuinely belong together or merely appear together. ' +
  'If the answer is a shared VPN or an exchange, it says nothing rather than naming the wrong machine.',

  'For each alert, work out which of those 141 numbers actually moved the score, and turn ' +
  'the top few into a sentence an analyst can act on.',

  'Save the alerts, the evidence and a receipt: the exact input file, the seed, the model, ' +
  'the commit. Every figure on screen can be traced back to all four.',
];
