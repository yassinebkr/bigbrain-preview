import { z } from 'zod';

const hash = z.string().regex(/^[a-f0-9]{64}$/);
const artifact = z.object({ path: z.string(), format: z.enum(['solidcraft', 'step', 'stl', 'png']),
  sha256: hash, size_bytes: z.number().int().positive(), source_sha256: hash.nullable() });
const document = z.object({ project_id: z.string(), document_id: z.string(), revision: z.number().int().positive(),
  engine_version: z.string(), engine_sha256: hash.nullable().optional(),
  units: z.literal('mm'), native: artifact, exports: z.array(artifact) });
const vector = z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]);
const snapshot = z.object({ document,
  geometry: z.object({ source_sha256: hash, body_count: z.number().int().nonnegative(), closed_solid: z.boolean(),
    bounds_min_mm: vector, bounds_max_mm: vector, volume_mm3: z.number().finite().nonnegative() }),
  preview: z.object({ project_id: z.string(), document_id: z.string(), revision: z.number().int().positive(),
    image: artifact, width: z.number().int().positive(), height: z.number().int().positive() }).nullable(),
  preview_state: z.enum(['current', 'stale', 'pending', 'failed', 'absent']), preview_error: z.string().nullable(),
  checks: z.array(z.object({ criterion_id: z.string(), status: z.enum(['passed', 'failed', 'inconclusive']),
    diagnostic: z.string(), evidence_ref: z.string(), source_sha256: hash,
    label: z.string().nullable().optional(), metric: z.enum(['dimensions_mm', 'volume_mm3', 'body_count', 'closed_solid', 'cylindrical_surface_mm', 'length_mm', 'angle_degree', 'point_mm']).nullable().optional(),
    observed: z.array(z.number().finite()).max(3).nullable().optional(), expected: z.array(z.number().finite()).max(3).nullable().optional(),
    absolute_tolerance: z.number().finite().nullable().optional(), relative_tolerance: z.number().finite().nullable().optional(),
    observed_intervals_mm: z.array(z.tuple([z.number().finite(), z.number().finite()])).max(16).nullable().optional(),
    expected_intervals_mm: z.array(z.tuple([z.number().finite(), z.number().finite()])).max(16).nullable().optional(),
  })).max(66).default([]) });
const view = z.object({ schema_version: z.literal('1.0'), document_id: z.string().regex(/^[a-f0-9]{32}$/),
  title: z.string(), sequence: z.number().int().positive(),
  status: z.enum(['modeling', 'checking', 'ready', 'failed', 'cancelled']),
  elapsed_seconds: z.number().finite().nonnegative(), snapshot: snapshot.nullable(), diagnostic: z.string().nullable(),
  working: z.object({
    checkpoint_id: z.string().regex(/^[a-f0-9]{32}$/),
    parent: z.string().regex(/^[a-f0-9]{32}$/).nullable(),
    contract_sha256: hash, engine_version: z.string(), engine_sha256: hash,
    native: artifact, mesh: artifact.nullable().optional(), accepted_steps: z.number().int().positive(),
    design: z.object({ params: z.array(z.unknown()), timeline: z.array(z.unknown()),
      sketches: z.array(z.unknown()), bodies: z.array(z.unknown()) }),
  }).nullable().optional(),
  execution: z.object({
    phase: z.enum(['deciding', 'discovering', 'observing', 'executing', 'checkpoint', 'repairing', 'revising']),
    current_step: z.string().nullable(), accepted_steps: z.number().int().nonnegative(),
    checkpoint: z.string().regex(/^[a-f0-9]{32}$/).nullable(), decisions: z.number().int().nonnegative(),
  }).nullable().optional(),
});

export type CadView = z.infer<typeof view>;

/** Display a separately published delivery while retaining the original task history. */
export function publishedCadView(cad: CadView, raw: unknown): CadView | undefined {
  const parsed = snapshot.safeParse(raw);
  if (!parsed.success || (raw as { delivery_status?: string })?.delivery_status !== 'ready') return;
  const result = parsed.data;
  const doc = result.document;
  if (doc.document_id !== cad.document_id || doc.project_id !== cad.document_id
    || (cad.snapshot && (doc.revision < cad.snapshot.document.revision
      || (doc.revision === cad.snapshot.document.revision && doc.native.sha256 !== cad.snapshot.document.native.sha256)))
    || result.geometry.source_sha256 !== doc.native.sha256 || !result.checks.length
    || result.checks.some(check => check.status !== 'passed' || check.source_sha256 !== doc.native.sha256)) return;
  return { ...cad, snapshot: result, status: 'ready', diagnostic: null };
}

export async function readPublishedCad(cad: CadView, sessionId: string, signal?: AbortSignal) {
  const response = await fetch('/api/cad/view', { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' },
    body: JSON.stringify({ documentId: cad.document_id, sessionId }) });
  if (!response.ok) return;
  return publishedCadView(cad, await response.json());
}

/** Retain exact CAD identity and monotonic checkpoints through live/replay events. */
export function cadUpdate(raw: unknown, previous?: CadView): CadView | undefined {
  const parsed = view.safeParse(raw);
  if (!parsed.success) return previous;
  const next = parsed.data;
  if (previous && (previous.document_id !== next.document_id || previous.sequence >= next.sequence
    || ['ready', 'failed', 'cancelled'].includes(previous.status))) return previous;
  const captured = next.snapshot;
  if (captured && (captured.document.document_id !== next.document_id
    || captured.geometry.source_sha256 !== captured.document.native.sha256)) return previous;
  return next;
}

export function currentCadPreview(cad: CadView) {
  const captured = cad.snapshot, preview = captured?.preview, doc = captured?.document;
  return !!(preview && doc && preview.project_id === doc.project_id && preview.document_id === doc.document_id
    && preview.revision === doc.revision && preview.image.source_sha256 === doc.native.sha256
    && cad.status === 'ready');
}

export async function cadArtifact(cad: CadView, sessionId: string, kind: string, signal?: AbortSignal) {
  const response = await fetch('/api/cad/artifact', { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' },
    body: JSON.stringify({ documentId: cad.document_id, sessionId,
      revision: cad.snapshot?.document.revision, kind }) });
  if (!response.ok) throw new Error((await response.json()).error || 'Artefact CAO indisponible');
  return response.blob();
}

export async function cadDesktop(cad: CadView, sessionId: string, action: 'open' | 'capability', signal?: AbortSignal) {
  const response = await fetch(`/api/cad/${action}`, { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' },
    body: JSON.stringify({ documentId: cad.document_id, sessionId, revision: cad.snapshot?.document.revision }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Ouverture SolidCraft indisponible');
  return result as { available?: boolean; diagnostic?: string; message?: string };
}


/** Read the accepted mesh whose bytes and native source are both bound to the checkpoint. */
export async function cadWorkingMesh(cad: CadView, sessionId: string, signal?: AbortSignal) {
  const working = cad.working;
  const mesh = working?.mesh;
  if (!working || !mesh || mesh.format !== 'stl' || mesh.source_sha256 !== working.native.sha256) {
    throw new Error('Le maillage ne correspond pas au point de reprise');
  }
  const response = await fetch('/api/cad/working-artifact', {
    method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' },
    body: JSON.stringify({ documentId: cad.document_id, sessionId, checkpointId: working.checkpoint_id, kind: 'stl' }),
  });
  if (!response.ok) throw new Error((await response.json()).error || 'Maillage de reprise indisponible');
  const bytes = await response.arrayBuffer();
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hash = Array.from(digest).map(value => value.toString(16).padStart(2, '0')).join('');
  if (hash !== mesh.sha256 || bytes.byteLength !== mesh.size_bytes) throw new Error('Identité du maillage modifiée');
  return bytes;
}


/** A published delivery selects its inspected export independently of construction history. */
export function cadMeshSource(cad: CadView): 'published' | 'checkpoint' | 'worker' | 'empty' {
  if (cad.status === 'ready' || !cad.working) return 'published';
  if (!cad.working.design.bodies.length) return 'empty';
  return cad.working.mesh ? 'checkpoint' : 'worker';
}
