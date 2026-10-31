import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it } from 'vitest';
import { cadUpdate, currentCadPreview } from '@/lib/cad';
import { surfaceRegistry } from '@/lib/morphable';
import { useAppStore, type RunState } from '@/store/appStore';
import { CadPanel } from './CadPanel';

function checkpoint(sequence = 1, status = 'ready') {
  const id = 'a'.repeat(32), source = 'b'.repeat(64);
  const native = { path: 'revision-1/part.sc', format: 'solidcraft', sha256: source, size_bytes: 500, source_sha256: null };
  return { schema_version: '1.0', document_id: id, title: 'Plaque de test', sequence, status, elapsed_seconds: 1,
    diagnostic: null, snapshot: {
      document: { project_id: id, document_id: id, revision: 1, engine_version: '0.28.0', units: 'mm', native,
        exports: [{ ...native, path: 'revision-1/part.step', format: 'step', source_sha256: source }] },
      geometry: { source_sha256: source, body_count: 1, closed_solid: true, bounds_min_mm: [0, 0, 0],
        bounds_max_mm: [60, 40, 6], volume_mm3: 14400 },
      preview: { project_id: id, document_id: id, revision: 1, width: 960, height: 600,
        image: { ...native, path: 'revision-1/preview.png', format: 'png', source_sha256: source } },
      preview_state: 'current', preview_error: null, checks: [{ criterion_id: 'dimensions', status: 'passed',
        diagnostic: 'Dimensions vérifiées', evidence_ref: 'measure.json', source_sha256: source }],
    } };
}
const run: RunState = { id: 'cad-run', sessionId: 'cad-session', description: 'Créer une pièce',
  status: 'running', startedAt: 1, files: [], steps: [] };
const event = (type: string, detail: Record<string, unknown>) => ({ type, detail });

beforeEach(() => useAppStore.setState({ activeSessionKey: run.sessionId, activeRun: null, sessionRuns: {},
  runsById: {}, completedRuns: [], sessionProposals: {} }));

describe('CAD piece surface', () => {
  it('presents actual dimensions, native and STEP actions, and measured checks', () => {
    const cad = cadUpdate(checkpoint())!;
    const html = renderToStaticMarkup(<CadPanel run={{ ...run, status: 'done', cad }} />);
    expect(html).toContain('60 × 40 × 6');
    expect(html).toContain('Révision 1');
    expect(html).toContain('Télécharger la pièce');
    expect(html).toContain('Ouvrir dans SolidCraft');
    expect(html).not.toContain('>STEP</button>');
    expect(html).toContain('Dimensions vérifiées');
    expect(html).not.toContain('Lancer le projet');
    expect(surfaceRegistry(run.sessionId, [{ ...run, cad }]).map(item => item.kind)).toEqual(['cad', 'activity']);
    expect(surfaceRegistry('another', [{ ...run, cad }])).toEqual([]);
  });
  it('keeps older geometry visibly distinct while a new revision is modeled', () => {
    const cad = cadUpdate(checkpoint(1, 'modeling'))!;
    expect(currentCadPreview(cad)).toBe(false);
    expect(renderToStaticMarkup(<CadPanel run={{ ...run, cad }} />)).toContain('aperçu antérieur');
    const changed = checkpoint();
    changed.snapshot.preview.revision = 2;
    expect(currentCadPreview(cadUpdate(changed)!)).toBe(false);
  });
  it('ignores out-of-order, cross-document and terminal-revival checkpoints', () => {
    const cad = cadUpdate(checkpoint(3, 'checking'))!;
    expect(cadUpdate(checkpoint(2), cad)).toBe(cad);
    expect(cadUpdate({ ...checkpoint(4), document_id: 'c'.repeat(32) }, cad)).toBe(cad);
    const ready = cadUpdate(checkpoint(4), cad)!;
    expect(cadUpdate(checkpoint(5, 'modeling'), ready)).toBe(ready);
    expect(cadUpdate({ ...checkpoint(4), snapshot: { ...checkpoint().snapshot,
      geometry: { ...checkpoint().snapshot.geometry, source_sha256: 'd'.repeat(64) } } }, cad)).toBe(cad);
  });
  it('shows an interrupted server run as stopped within the piece surface', () => {
    const cad = cadUpdate(checkpoint(1, 'checking'))!;
    const html = renderToStaticMarkup(<CadPanel run={{ ...run, status: 'failed', error: 'Serveur redémarré', cad }} />);
    expect(html).toContain('Modélisation à reprendre');
    expect(html).toContain('Serveur redémarré');
    expect(html).not.toContain('Mesures et vérifications');
  });
  it('correlates live and restored CAD data with its run and conversation', () => {
    const store = useAppStore.getState();
    store.applyRunEvent(event('task.received', { task_id: run.id, session_id: run.sessionId, description: run.description }));
    const detail = { task_id: run.id, session_id: run.sessionId, subtask_id: 'cad-step', brain: 'cad_brain', cad: checkpoint() };
    store.applyRunEvent(event('task.progress', { ...detail, brain: 'python_brain_0' }));
    expect(useAppStore.getState().runsById[run.id].cad).toBeUndefined();
    store.applyRunEvent(event('task.progress', detail));
    expect(useAppStore.getState().runsById[run.id].cad?.title).toBe('Plaque de test');
    store.applyRunEvent(event('task.complete', { task_id: run.id, session_id: run.sessionId, result_kind: 'cad' }));
    expect(useAppStore.getState().completedRuns[0].cad?.status).toBe('ready');
    store.applyRunEvent(event('task.progress', { ...detail, session_id: 'another' }));
    expect(useAppStore.getState().completedRuns[0].sessionId).toBe(run.sessionId);
  });
});
