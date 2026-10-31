import { z } from 'zod';

const hash = z.string().regex(/^[a-f0-9]{64}$/);
const artifact = z.object({ path: z.string(), format: z.enum(['solidcraft', 'step', 'stl', 'png']),
  sha256: hash, size_bytes: z.number().int().positive(), source_sha256: hash.nullable() });
const document = z.object({ project_id: z.string(), document_id: z.string(), revision: z.number().int().positive(),
  engine_version: z.string(), units: z.literal('mm'), native: artifact, exports: z.array(artifact) });
const vector = z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]);
const snapshot = z.object({ document,
  geometry: z.object({ source_sha256: hash, body_count: z.number().int().nonnegative(), closed_solid: z.boolean(),
    bounds_min_mm: vector, bounds_max_mm: vector, volume_mm3: z.number().finite().nonnegative() }),
  preview: z.object({ project_id: z.string(), document_id: z.string(), revision: z.number().int().positive(),
    image: artifact, width: z.number().int().positive(), height: z.number().int().positive() }).nullable(),
  preview_state: z.enum(['current', 'stale', 'pending', 'failed', 'absent']), preview_error: z.string().nullable(),
  checks: z.array(z.object({ criterion_id: z.string(), status: z.enum(['passed', 'failed', 'inconclusive']),
    diagnostic: z.string(), evidence_ref: z.string(), source_sha256: hash })).max(64).default([]) });
const view = z.object({ schema_version: z.literal('1.0'), document_id: z.string().regex(/^[a-f0-9]{32}$/),
  title: z.string(), sequence: z.number().int().positive(),
  status: z.enum(['modeling', 'checking', 'ready', 'failed', 'cancelled']),
  elapsed_seconds: z.number().finite().nonnegative(), snapshot: snapshot.nullable(), diagnostic: z.string().nullable() });

export type CadView = z.infer<typeof view>;

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
