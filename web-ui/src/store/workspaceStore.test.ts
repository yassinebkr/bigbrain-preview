import { beforeEach, expect, it } from 'vitest';
import { useWorkspaceStore } from './workspaceStore';

beforeEach(() => useWorkspaceStore.setState({ sessions: {} }));

it('accepts a widget snapshot without moving focus and does not follow later revisions', () => {
  const run = { id: 'r', sessionId: 's', description: 'Tool', status: 'running' as const, startedAt: 1, files: [], steps: [], widgetProposal: { version: 1 as const, revision: 1, widgets: ['files' as const] } };
  const store = useWorkspaceStore.getState();
  store.update('s', { mode: 'workspace', selectedId: 's/other/files', width: 480 });
  store.acceptWidgets(run);
  run.widgetProposal = { ...run.widgetProposal, revision: 2 };
  expect(useWorkspaceStore.getState().sessions.s).toMatchObject({ selectedId: 's/other/files', width: 480, widgetChoices: { r: { revision: 1, widgets: ['files'] } } });
  store.resetWidgets(run);
  expect(useWorkspaceStore.getState().sessions.s.widgetChoices).toEqual({});
});

it('isolates choices by conversation', () => {
  const store = useWorkspaceStore.getState();
  store.update('first', { mode: 'workspace', selectedId: 'first/run/files', width: 420 });
  store.update('second', { mode: 'focus' });
  expect(useWorkspaceStore.getState().sessions.first).toEqual({ mode: 'workspace', selectedId: 'first/run/files', width: 420 });
  expect(useWorkspaceStore.getState().sessions.second).toEqual({ mode: 'focus' });
});

it('closes without losing selected surface or width', () => {
  const store = useWorkspaceStore.getState();
  store.update('first', { mode: 'workspace', selectedId: 'first/run/activity', width: 460 });
  store.update('first', { mode: 'peek' });
  expect(useWorkspaceStore.getState().sessions.first).toEqual({ mode: 'peek', selectedId: 'first/run/activity', width: 460 });
});

it('opens web results on the preview, other tasks on activity', () => {
  const run = { id: 'web', sessionId: 's', description: 'Demo', status: 'done' as const, startedAt: 1, files: [], steps: [], projectPath: 'sandbox/demo', entryPoint: 'index.html', deliverableType: 'web_app', runnable: true };
  useWorkspaceStore.getState().inspect(run);
  expect(useWorkspaceStore.getState().sessions.s.selectedId).toBe('s/web/preview');
  useWorkspaceStore.getState().inspect({ ...run, resultKind: 'taskboard' });
  expect(useWorkspaceStore.getState().sessions.s.selectedId).toBe('s/web/activity');
});

it('returns from activity-first to chat without losing the object or side width', () => {
  const store = useWorkspaceStore.getState();
  store.update('first', { mode: 'expanded', selectedId: 'first/run/files', width: 520 });
  store.update('first', { mode: 'workspace' });
  expect(useWorkspaceStore.getState().sessions.first).toEqual({ mode: 'workspace', selectedId: 'first/run/files', width: 520 });
  store.update('first', { mode: 'focus' });
  expect(useWorkspaceStore.getState().sessions.first.selectedId).toBe('first/run/files');
});
