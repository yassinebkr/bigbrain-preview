import { expect, it } from 'vitest';
import { composeWidgets, parseWidgetProposal } from './widgetPolicy';
import type { RunState } from '@/store/appStore';

const run: RunState = { id: 'run', sessionId: 's', description: 'tool', status: 'done', startedAt: 1, steps: [], files: [{ path: 'sandbox/tool/main.py', ts: 1 }], projectPath: 'sandbox/tool', entryPoint: 'main.py', deliverableType: 'python', runnable: true };
it('rejects geometry, actions, unknown catalogs, duplicates and bad versions', () => {
  const valid = { version: 1, revision: 1, widgets: ['console'] };
  expect(parseWidgetProposal(valid)).toEqual(valid);
  for (const proposal of [{ ...valid, width: 1000 }, { ...valid, execute: true }, { ...valid, version: 2 }, { ...valid, revision: 0 }, { ...valid, widgets: ['html'] }, { ...valid, widgets: ['files', 'files'] }]) expect(parseWidgetProposal(proposal)).toBeUndefined();
});
it('only projects available data, without inventing a preview or evidence', () => {
  expect(composeWidgets(run, ['preview', 'verification'])).toEqual([]);
  expect(composeWidgets(run, ['files'])).toEqual(['files']);
  expect(composeWidgets({ ...run, resultKind: 'taskboard' }, ['console', 'files'])).toEqual([]);
});
it('protects a consulted console and failed verification within two slots', () => {
  const failed = { ...run, verification: { runId: 'proof', verdict: 'failed' as const, stages: [] } };
  expect(composeWidgets(failed, ['files'], true)).toEqual(['console', 'verification']);
});
