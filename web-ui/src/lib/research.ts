import { z } from 'zod';

const evidence = z.object({ passage_id: z.string(), relation: z.enum(['supports', 'contradicts', 'context']) });
const citation = evidence.extend({ quote: z.string(), explanation: z.string(), direct: z.boolean() });
const sourceAssessment = z.object({ source_id: z.string(), kind: z.string(), nature: z.string(),
  suitability: z.string(), basis: z.string(), limitations: z.array(z.string()), origin_urls: z.array(z.string()) });
const selection = z.object({ status: z.string(), method: z.string(), coverage: z.string(),
  characters_selected: z.number(), characters_available: z.number(), group_count: z.number(),
  selected_group_ids: z.array(z.string()), omitted_group_count: z.number().optional(),
  omitted_group_ids: z.array(z.string()), partial_group_ids: z.array(z.string()).optional(),
  catalog_truncated: z.boolean().optional(),
  catalog: z.array(z.object({ id: z.string(), context: z.array(z.string()), characters: z.number() })) });
const acquisition = z.object({ mode: z.string().optional(), status: z.string().optional(),
  captured_at: z.string().optional(), title: z.string().optional(), cache_hit: z.boolean().optional(),
  limitations: z.array(z.string()).optional(), engine: z.string().optional(), selection: selection.optional() });
const passage = z.object({ id: z.string(), source_id: z.string(), text: z.string(),
  kind: z.string().optional(), context: z.array(z.string()).optional(), clipped: z.boolean().optional(),
  observation_sha256: z.string().nullable().optional(), review_only: z.boolean().optional() });
const historyItem = z.object({ index: z.number().int().nonnegative(), tool: z.string(), rationale: z.string(),
  status: z.string(), error: z.string().nullable().optional() });
const snapshot = z.object({
  delivery_mode: z.enum(['reviewed', 'documentary']).optional(),
  review_reason: z.string().nullable().optional(),
  research_id: z.string().min(1).max(80),
  attempt_id: z.string().nullable().optional(),
  answer_status: z.enum(['unassessed', 'partial', 'complete']).optional(),
  execution_outcome: z.enum(['running', 'complete', 'partial', 'blocked', 'cancelled', 'interrupted', 'failed', 'clarification']).optional(),
  workflow: z.object({ version: z.string().optional(), stage: z.string().optional(),
    complement_used: z.boolean().optional(), outcome: z.string().optional() }).optional(),
  original_request_coverage: z.object({ complete: z.boolean().optional(), gaps: z.array(z.string()).optional() }).optional(),
  question_coverage: z.array(z.object({ question_id: z.string(), status: z.string(),
    claim_ids: z.array(z.string()), missing_evidence: z.array(z.string()), rationale: z.string() })).optional(),
  schema_version: z.literal('1.0'), revision: z.number().int().nonnegative(), objective: z.string(),
  status: z.enum(['running', 'completed', 'partial', 'unavailable', 'clarification', 'cancelled']),
  reason: z.string().nullable(), assessment_error: z.string().nullable(),
  diagnostic: z.object({ contract: z.string().optional(), code: z.string(),
    type: z.string().optional(), message: z.string().optional(),
    delivery_error: z.object({ stage: z.string(), type: z.string(), message: z.string() }).optional(),
    checkpoint_error: z.object({ type: z.string(), message: z.string() }).optional(),
    errors: z.array(z.object({ type: z.string(), field: z.string() })).optional() }).nullable().optional(),
  questions: z.array(z.object({ id: z.string(), text: z.string(), evidence_needed: z.string(), freshness: z.string() })).max(6),
  sources: z.array(z.object({ id: z.string(), url: z.string(), title: z.string(), status: z.string(),
    final_url: z.string().nullable(), consulted_at: z.string().nullable(), source_kind: z.string(),
    truncated: z.boolean(), error: z.string().nullable(), acquisition: acquisition.optional() })).max(25),
  // Reader byte/page bounds belong to the runtime. An arbitrary UI item ceiling
  // must not discard the entire terminal snapshot of a legitimate long page.
  passages: z.array(passage).optional(),
  history: z.array(historyItem).optional(),
  activity: z.object({ stage: z.string(), phase: z.string().optional(), source_id: z.string().optional(),
    mode: z.string().optional(), request_index: z.number().optional(), resource_type: z.string().optional() }).nullable().optional(),
  claims: z.array(z.object({ id: z.string(), question_id: z.string(), text: z.string(),
    status: z.enum(['supported', 'contested', 'unverified', 'refuted']), basis: z.string(),
    evidence: z.array(evidence), limitations: z.array(z.string()), scope: z.string(),
    reasoning: z.enum(['direct', 'qualified_inference']).optional() })).max(12),
  assessments: z.array(z.object({ claim_id: z.string(), relevant: z.boolean(), rationale: z.string(),
    citations: z.array(citation), origin_groups: z.record(z.string(), z.string()), source_assessments: z.array(sourceAssessment) })).optional(),
  usage: z.object({ model_calls: z.number().optional(), unknown_usage_calls: z.number().optional(),
    reported_tokens: z.number().optional(), cached_input_tokens: z.number().optional(),
    allowance_used: z.number().optional(), cost_usd: z.number().nullable().optional(),
    reported_usage: z.object({ input_tokens: z.number().nullable(), output_tokens: z.number().nullable(),
      cached_input_tokens: z.number().nullable() }).optional(),
    stage_budget: z.object({ input_units: z.number(), output_units: z.number(), logical_calls: z.number(),
      input_limit: z.number(), output_limit: z.number(), call_limit: z.number(),
      policy: z.string().optional(), threshold_exceeded: z.boolean().optional(),
      excess_input_units: z.number().optional(), excess_output_units: z.number().optional() }).optional(),
    api_reference: z.object({ measured_subtotal_usd: z.number(), priced_records: z.number(),
      logical_calls: z.number(), complete: z.boolean() }).optional() }),
  limits: z.object({ actions: z.number(), searches: z.number(), pages: z.number(), browsers: z.number().optional(), reviews: z.number().optional(), seconds: z.number(), tokens: z.number() }),
  counts: z.object({ searches: z.number(), pages: z.number(), browsers: z.number().optional(), reviews: z.number().optional() }), elapsed_seconds: z.number(),
  current_action: z.object({ tool: z.string(), rationale: z.string(), query: z.string().nullable(),
    source_id: z.string().nullable(), focus: z.string().nullable().optional(), group_ids: z.array(z.string()).optional() }).nullable(),
});
const observation = z.object({ index: z.number().int().nonnegative(), status: z.string(),
  action: z.object({ tool: z.string(), rationale: z.string() }),
  data: z.object({ passages: snapshot.shape.passages, error: z.string().optional() }) });
type Snapshot = z.infer<typeof snapshot>;
export type ResearchView = Omit<Snapshot, 'passages' | 'assessments'> & {
  received_at_ms?: number;
  passages: NonNullable<Snapshot['passages']>; assessments: NonNullable<Snapshot['assessments']>;
  history: z.infer<typeof historyItem>[];
};

/** Distinguish bounded documentary gaps from transport or contract failures. */
export function isPartialResearch(run: { status: string; projectPath?: string; files: unknown[];
  researches?: Record<string, Pick<ResearchView, 'status' | 'execution_outcome' | 'diagnostic'>> }) {
  if (run.status !== 'failed' || run.projectPath || run.files.length) return false;
  const records = Object.values(run.researches || {});
  const bounded = new Set(['direct_budget', 'budget', 'budget_exhausted', 'deadline', 'time_budget_exhausted']);
  return records.some((record) => record.status === 'partial') && records.every((record) =>
    ['partial', 'completed'].includes(record.status) && record.execution_outcome !== 'failed'
    && (!record.diagnostic || bounded.has(record.diagnostic.code)));
}

const reviewEvidence = z.object({ stage: z.literal('research_review_evidence'), passages: z.array(passage) });

export function researchUpdate(raw: unknown, previous?: ResearchView, observed?: unknown, progress?: unknown): ResearchView | undefined {
  const result = snapshot.safeParse(raw);
  if (!result.success || previous && result.data.revision <= previous.revision) return previous;
  const data = result.data;
  // A stale checkpoint cannot revive an already terminal research subtask.
  const newAttempt = data.attempt_id && previous?.attempt_id && data.attempt_id !== previous.attempt_id;
  if (previous && previous.status !== 'running' && data.status === 'running' && !newAttempt) return previous;
  let passages = data.passages || previous?.passages || [];
  let history = data.history || previous?.history || [];
  // Review supplements are real observed blocks too. Keep them during the run,
  // before the final checkpoint, and deduplicate event replay by passage ID.
  const review = reviewEvidence.safeParse(progress);
  if (review.success) passages = [...new Map([...passages, ...review.data.passages].map((p) => [p.id, p])).values()];
  const obs = observation.safeParse(observed);
  if (obs.success) {
    passages = [...new Map([...passages, ...(obs.data.data.passages || [])].map((p) => [p.id, p])).values()];
    // Batch children share a parent decision index; retain their passages as
    // they arrive, but leave the history row to the enclosing batch operation.
    if (!(progress && typeof progress === 'object' && 'stage' in progress && progress.stage === 'research_batch_observation')) {
      history = [...history.filter((item) => item.index !== obs.data.index), { index: obs.data.index,
        tool: obs.data.action.tool, rationale: obs.data.action.rationale, status: obs.data.status, error: obs.data.data.error }].slice(-20);
    }
  }
  return { ...data, received_at_ms: Date.now(), passages, assessments: data.assessments || previous?.assessments || [], history };
}

/** Interpolate display time only; terminal snapshots remain authoritative. */
export function researchElapsed(research: ResearchView, live: boolean, now: number, received: number) {
  if (!live || research.status !== 'running') return research.elapsed_seconds;
  return Math.max(research.elapsed_seconds, Math.min(research.limits.seconds,
    research.elapsed_seconds + Math.max(0, now - received) / 1000));
}

export function publicLink(url: string) {
  try { const value = new URL(url); return ['http:', 'https:'].includes(value.protocol) && !value.username && !value.password ? value.href : undefined; }
  catch { return undefined; }
}
