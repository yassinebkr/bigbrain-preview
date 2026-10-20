import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useAppStore, type RunState } from './appStore';
import { projectRunKey, pythonEntry, useProjectRunStore } from './projectRunStore';

const run: RunState = { id: 'python', sessionId: 's1', description: 'Actual project', status: 'done', startedAt: 1, files: [], steps: [], projectPath: 'sandbox/tool', entryPoint: 'main.py', deliverableType: 'python', runnable: true };
beforeEach(() => { useProjectRunStore.setState({ launches: {} }); useAppStore.setState({ liveRuns: {} }); });
afterEach(() => vi.unstubAllGlobals());

it('only exposes a verified Python entry, never board or web metadata', () => {
  expect(pythonEntry(run)).toBe('sandbox/tool/main.py');
  for (const change of [{ runnable: false }, { status: 'failed' as const }, { resultKind: 'taskboard' }, { deliverableType: 'web_app' }]) expect(pythonEntry({ ...run, ...change })).toBeUndefined();
});

it('correlates early WS output and suppresses duplicate launches until the result', async () => {
  const request = vi.fn(async (_url: RequestInfo | URL, _options?: RequestInit) => {
    useAppStore.getState().applyFsRunEvent({ type: 'fs.run_output', detail: { runId: 'fs1', delta: 'early output' } });
    return { ok: true, json: async () => ({ runId: 'fs1' }) };
  });
  vi.stubGlobal('fetch', request);
  await useProjectRunStore.getState().launch(run);
  await useProjectRunStore.getState().launch(run);
  expect(request).toHaveBeenCalledTimes(1);
  expect(JSON.parse(request.mock.calls[0][1]!.body as string)).toEqual({ path: 'sandbox/tool/main.py' });
  expect(useAppStore.getState().liveRuns.fs1.out).toBe('early output');
  useAppStore.getState().applyFsRunEvent({ type: 'fs.run_result', detail: { runId: 'fs1', exitCode: 0 } });
  await useProjectRunStore.getState().launch(run);
  expect(request).toHaveBeenCalledTimes(2);
});

it('blocks a second click before the first WS event', async () => {
  const request = vi.fn(async () => ({ ok: true, json: async () => ({ runId: 'waiting' }) }));
  vi.stubGlobal('fetch', request);
  await useProjectRunStore.getState().launch(run);
  await useProjectRunStore.getState().launch(run);
  expect(request).toHaveBeenCalledTimes(1);
});

it('keeps launches isolated by session and surfaces HTTP errors without inventing output', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 403, json: async () => ({ error: 'Permission refusée' }) })));
  await useProjectRunStore.getState().launch(run);
  expect(useProjectRunStore.getState().launches[projectRunKey(run)].error).toContain('Permission refusée');
  expect(useProjectRunStore.getState().launches[projectRunKey({ ...run, sessionId: 's2' })]).toBeUndefined();
  expect(useAppStore.getState().liveRuns).toEqual({});
});
