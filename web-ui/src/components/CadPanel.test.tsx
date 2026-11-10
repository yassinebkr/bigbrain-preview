import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it } from 'vitest';
import { cadUpdate, currentCadPreview, publishedCadView } from '@/lib/cad';
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
  it('shares a verified publication across mirrors while retaining the failed attempt', () => {
    const failed: RunState = { ...run, status: 'failed', deliveryStatus: 'incomplete',
      error: 'Old preflight failure', cad: cadUpdate(checkpoint(3, 'failed'))!,
      steps: [{ id: 'step', status: 'failed', description: 'Construire' }] };
    useAppStore.setState({ activeRun: failed, sessionRuns: { [run.sessionId]: failed },
      runsById: { [run.id]: failed }, completedRuns: [failed] });
    const publish = publishedCadView(failed.cad!, { ...checkpoint().snapshot, delivery_status: 'ready' })!;
    const reconcile = useAppStore.getState().reconcileCadPublication;
    reconcile(run.id, 'other-session', publish);
    expect(useAppStore.getState().activeRun).toBe(failed);
    reconcile(run.id, run.sessionId, publish);
    const state = useAppStore.getState();
    for (const current of [state.activeRun, state.sessionRuns[run.sessionId], state.runsById[run.id], state.completedRuns[0]]) {
      expect(current?.status).toBe('done');
      expect(current?.deliveryStatus).toBe('ready');
      expect(current?.error).toBeUndefined();
      expect(current?.previousAttempt?.error).toBe('Old preflight failure');
      expect(current?.previousAttempt?.steps[0].status).toBe('failed');
      expect(current?.verification?.verdict).toBe('passed');
    }
    reconcile(run.id, run.sessionId, publish);
    expect(useAppStore.getState().activeRun?.previousAttempt).toBe(state.activeRun?.previousAttempt);
    useAppStore.getState().applyRunEvent(event('task.failed', {
      task_id: run.id, session_id: run.sessionId, error: 'Old preflight failure', delivery_status: 'incomplete',
    }));
    expect(useAppStore.getState().sessionRuns[run.sessionId].deliveryStatus).toBe('ready');
    expect(useAppStore.getState().sessionRuns[run.sessionId].status).toBe('done');
  });
  it('reconciles a published delivery without reviving the failed task event', () => {
    const failed = cadUpdate(checkpoint(3, 'failed'))!;
    const source = { ...checkpoint().snapshot, delivery_status: 'ready' };
    const display = publishedCadView(failed, source)!;
    expect(display.status).toBe('ready');
    expect(display.snapshot?.checks).toHaveLength(1);
    expect(failed.status).toBe('failed');
    expect(cadUpdate(checkpoint(4), failed)).toBe(failed);
    expect(publishedCadView(failed, { ...source, delivery_status: 'incomplete' })).toBeUndefined();
    expect(publishedCadView(failed, { ...source, checks: [] })).toBeUndefined();
    expect(publishedCadView(failed, { ...source, document: { ...source.document, document_id: 'f'.repeat(32) } })).toBeUndefined();
    expect(publishedCadView(failed, { ...source, checks: [{ ...source.checks[0], status: 'failed' }] })).toBeUndefined();
    expect(publishedCadView(failed, { ...source, geometry: { ...source.geometry, source_sha256: 'c'.repeat(64) } })).toBeUndefined();
  });
  it('renders 64 proposed checks and the two mandatory runtime checks', () => {
    const value = checkpoint();
    value.snapshot.checks = Array.from({ length: 66 }, (_, i) => ({
      ...value.snapshot.checks[0], criterion_id: `check-${i}`, diagnostic: `Measured check ${i}`,
    }));
    const cad = cadUpdate(value)!;
    expect(cad.snapshot?.checks).toHaveLength(66);
    const html = renderToStaticMarkup(<CadPanel run={{ ...run, status: 'done', cad }} />);
    expect(html).toContain('66/66 conformes');
    expect(html).toContain('Measured check 65');
  });
  it('shows the observed construction step and retained count during work', () => {
    const cad = cadUpdate({ ...checkpoint(1, 'modeling'), execution: {
      phase: 'observing', current_step: 'Esquisse du perçage', accepted_steps: 2,
      checkpoint: 'e'.repeat(32), decisions: 4,
    } })!;
    const html = renderToStaticMarkup(<CadPanel run={{ ...run, cad }} />);
    expect(html).toContain('Inspection de la géométrie');
    expect(html).toContain('Esquisse du perçage');
    expect(html).toContain('2 étapes');
    expect(html).toContain('vérifications de la pièce complète');
    expect(html).not.toContain('e'.repeat(32));
    expect(cadUpdate({ ...checkpoint(2, 'modeling'), execution: {
      phase: 'ready', accepted_steps: 3,
    } }, cad)).toBe(cad);
  });
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
  it('updates the Atelier construction phase through actual run event handling', () => {
    const store = useAppStore.getState();
    store.applyRunEvent(event('task.received', { task_id: run.id, session_id: run.sessionId, description: run.description }));
    for (const [index, phase] of ['deciding', 'executing', 'checkpoint', 'observing'].entries()) {
      store.applyRunEvent(event('task.progress', { task_id: run.id, session_id: run.sessionId,
        subtask_id: 'cad-step', brain: 'cad_brain', cad: { ...checkpoint(index + 1, 'modeling'),
          execution: { phase, current_step: 'Socle', accepted_steps: phase === 'checkpoint' || phase === 'observing' ? 1 : 0,
            checkpoint: phase === 'checkpoint' || phase === 'observing' ? 'e'.repeat(32) : null, decisions: index + 1 } } }));
      expect(useAppStore.getState().runsById[run.id].cad?.execution?.phase).toBe(phase);
    }
    const cad = useAppStore.getState().runsById[run.id].cad!;
    const html = renderToStaticMarkup(<CadPanel run={{ ...run, cad }} />);
    expect(html).toContain('Inspection de la géométrie');
    expect(html).toContain('Socle');
    expect(cad.execution?.accepted_steps).toBe(1);
  });
});
