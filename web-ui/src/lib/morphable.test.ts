import { describe, expect, it } from 'vitest';
import { nextProjectAttempt, reconcileWorkspace, surfaceId, surfaceRegistry } from './morphable';
import type { RunState } from '@/store/appStore';

const run: RunState = { id: 'web', sessionId: 's1', description: 'Actual web run', status: 'running', startedAt: 1, steps: [], files: [] };

describe('deterministic workspace reconciler', () => {
  it('follows a new projectless research after a closed run, without switching concurrent work', () => {
    const old = { ...run, status: 'failed' as const, startedAt: 1, finishedAt: 4 };
    const retry = { ...run, id: 'research-retry', startedAt: 5 };
    expect(nextProjectAttempt(old, surfaceRegistry('s1', [old, retry]))?.run.id).toBe('research-retry');
    expect(nextProjectAttempt({ ...old, status: 'running' }, surfaceRegistry('s1', [old, retry]))).toBeUndefined();
    expect(nextProjectAttempt(old, surfaceRegistry('s1', [old, { ...retry, startedAt: 3 }]))).toBeUndefined();
    expect(nextProjectAttempt(old, surfaceRegistry('s1', [old, { ...retry, resultKind: 'taskboard' }]))).toBeUndefined();
    expect(nextProjectAttempt(old, surfaceRegistry('s1', [old, retry]), 6)).toBeUndefined();
  });
  it('follows a repair of the same project through planning and failure, not unrelated work', () => {
    const old = { ...run, projectPath: 'sandbox/gcode', status: 'failed' as const };
    const repair = { ...old, id: 'repair', startedAt: 2 };
    const board = { ...run, id: 'board', startedAt: 3, resultKind: 'taskboard' };
    for (const status of ['running', 'failed'] as const) {
      expect(nextProjectAttempt(old, surfaceRegistry('s1', [old, { ...repair, status }, board]))?.run.id).toBe('repair');
    }
    expect(nextProjectAttempt(old, surfaceRegistry('s1', [old, board]))).toBeUndefined();
    expect(nextProjectAttempt(old, surfaceRegistry('s2', [{ ...repair, sessionId: 's2' }]))).toBeUndefined();
    expect(nextProjectAttempt({ ...old, projectPath: undefined }, surfaceRegistry('s1', [repair]))?.run.id).toBe('repair');
    expect(nextProjectAttempt({ ...old, projectPath: undefined, status: 'running' }, surfaceRegistry('s1', [repair]))).toBeUndefined();
    expect(nextProjectAttempt(old, surfaceRegistry('s1', [repair]), 3)).toBeUndefined();
    expect(nextProjectAttempt(old, surfaceRegistry('s1', [{ ...repair, startedAt: 4 }]), 3)?.run.id).toBe('repair');
  });
  it('keeps simple conversations in focus without fabricating artifacts', () => {
    expect(surfaceRegistry(null, [run])).toEqual([]);
    expect(reconcileWorkspace(surfaceRegistry('empty', [run])).mode).toBe('focus');
  });
  it('offers peek, never forces workspace on a new run', () => {
    expect(reconcileWorkspace(surfaceRegistry('s1', [run])).mode).toBe('peek');
    expect(reconcileWorkspace(surfaceRegistry('s1', [run]), { mode: 'focus' }).mode).toBe('focus');
  });
  it('uses a closed catalog derived from real data and deduplicates restored runs', () => {
    const real = { ...run, files: [{ path: 'sandbox/web/main.py', ts: 1 }], verification: { runId: 'proof', verdict: 'failed' as const, stages: [] } };
    const surfaces = surfaceRegistry('s1', [real, run, { ...real, sessionId: 'other', id: 'other' }]);
    expect(surfaces.map((s) => s.kind)).toEqual(['activity', 'files', 'verification']);
    expect(surfaces[0].run).toBe(real);
  });
  it('does not steal an explicit selection on concurrent tasks, error or completion', () => {
    const preference = { mode: 'workspace' as const, selectedId: surfaceId(run, 'activity') };
    for (const status of ['running', 'failed', 'done'] as const) {
      const state = reconcileWorkspace(surfaceRegistry('s1', [{ ...run, status }, { ...run, id: 'board', startedAt: 2 }]), preference);
      expect(state.selected?.run.id).toBe('web');
      expect(state.mode).toBe('workspace');
    }
  });
  it('never falls back to a foreign or disappeared selection while restoring', () => {
    const state = reconcileWorkspace(surfaceRegistry('s1', [run]), { mode: 'workspace', selectedId: 'foreign/run/activity' });
    expect(state.selected).toBeUndefined();
    expect(state.mode).toBe('workspace');
  });
  it('keeps activity-first layout user-owned through completion and concurrent runs', () => {
    const preference = { mode: 'expanded' as const, selectedId: surfaceId(run, 'activity'), width: 520 };
    const state = reconcileWorkspace(surfaceRegistry('s1', [
      { ...run, status: 'done' }, { ...run, id: 'parallel', startedAt: 2 },
    ]), preference);
    expect(state.mode).toBe('expanded');
    expect(state.selected?.run.id).toBe(run.id);
    expect(state.width).toBe(520);
  });
  it('keeps closing distinct from destroying and bounds width', () => {
    const surfaces = surfaceRegistry('s1', [run]);
    const id = surfaces[0].id;
    expect(reconcileWorkspace(surfaces, { mode: 'peek', selectedId: id, width: 9999 })).toMatchObject({ selected: surfaces[0], width: 1000 });
    expect(reconcileWorkspace(surfaces, { mode: 'workspace', selectedId: id, width: 12 }).width).toBe(400);
    expect(reconcileWorkspace(surfaces, { width: NaN }).width).toBe(400);
  });
  it('offers a preview only for a verified runnable web result, never board metadata', () => {
    const web = { ...run, status: 'done' as const, runnable: true, deliverableType: 'web_app', projectPath: 'sandbox/demo', entryPoint: 'index.html' };
    expect(surfaceRegistry('s1', [web])[0].kind).toBe('preview');
    expect(surfaceRegistry('s1', [{ ...web, runnable: false }]).some((s) => s.kind === 'preview')).toBe(false);
    expect(surfaceRegistry('s1', [{ ...web, status: 'failed' }]).some((s) => s.kind === 'preview')).toBe(false);
    expect(surfaceRegistry('s1', [{ ...web, resultKind: 'taskboard' }]).some((s) => s.kind === 'preview')).toBe(false);
  });
});
