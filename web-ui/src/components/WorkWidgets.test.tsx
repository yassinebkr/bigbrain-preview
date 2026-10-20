import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, expect, it, vi } from 'vitest';
import { PythonConsole, WorkOverview } from './WorkWidgets';
import { useAppStore, type RunState } from '@/store/appStore';
import { projectRunKey, useProjectRunStore } from '@/store/projectRunStore';

// Read current snapshots in these server-rendered component tests. Zustand's
// real browser subscription is exercised separately by Chromium acceptance.
vi.mock('@/store/appStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/appStore')>();
  return { ...actual, useAppStore: Object.assign((selector: (state: ReturnType<typeof actual.useAppStore.getState>) => unknown) => selector(actual.useAppStore.getState()), actual.useAppStore) };
});
vi.mock('@/store/projectRunStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/projectRunStore')>();
  return { ...actual, useProjectRunStore: Object.assign((selector: (state: ReturnType<typeof actual.useProjectRunStore.getState>) => unknown) => selector(actual.useProjectRunStore.getState()), actual.useProjectRunStore) };
});

const run: RunState = { id: 'python', sessionId: 's', description: 'Build tool', status: 'done', startedAt: 1, files: [{ path: 'sandbox/tool/main.py', ts: 1 }], steps: [], runnable: true, deliverableType: 'python', projectPath: 'sandbox/tool', entryPoint: 'main.py' };
const overview = (value: RunState) => renderToStaticMarkup(<WorkOverview run={value} select={() => {}} journal={<p>real journal</p>} />);
beforeEach(() => {
  useProjectRunStore.setState({ launches: {} }); useAppStore.setState({ liveRuns: {}, sessionProposals: {}, contractProposal: null });
});

it('composes a usable Python result without inventing reports or verification', () => {
  const html = overview(run);
  expect(html).toContain('Lancer le projet');
  expect(html).toContain('Ouvrir le projet');
  expect(html).toContain('1 fichier disponible');
  expect(html).not.toContain('Vérifications réussies');
  expect(html).not.toContain('<iframe');
});
it('never gives project launch controls to a board task', () => {
  const html = overview({ ...run, resultKind: 'taskboard' });
  expect(html).toContain('Ouvrir la taskboard');
  expect(html).not.toContain('Lancer le projet');
});
it('only renders the proposal belonging to the selected run', () => {
  useAppStore.setState({ sessionProposals: { s: { planId: 'other', designId: 'd', request: 'other', contracts: ['foreign secret'] } } });
  const html = overview({ ...run, awaitingApproval: true, status: 'running' });
  expect(html).not.toContain('foreign secret');
  expect(html).not.toContain('Approuver et lancer');
});
it('shows actual acceptance criteria and frozen target with explicit approval', () => {
  const proposal = { planId: 'python', designId: 'design1', request: 'Build tool', contracts: ['Respecter les données inconnues', 'Ne pas commander l’imprimante'], target: { mode: 'new', path: 'sandbox/tool' } };
  useAppStore.setState({ sessionProposals: { s: proposal }, contractProposal: proposal });
  const html = overview({ ...run, awaitingApproval: true, status: 'running' });
  expect(html).toContain('Respecter les données inconnues');
  expect(html).toContain('Approuver et lancer');
  expect(html).toContain('sandbox/tool');
});
it('renders real console output, exit code and failures safely', () => {
  useProjectRunStore.setState({ launches: { [projectRunKey(run)]: { runId: 'fs1', pending: false } } });
  useAppStore.setState({ liveRuns: { fs1: { out: '<script>unsafe()</script>', err: 'failure details', done: true, result: { exitCode: 2 } } } });
  const html = renderToStaticMarkup(<PythonConsole run={run} />);
  expect(html).toContain('&lt;script&gt;');
  expect(html).not.toContain('<script>');
  expect(html).toContain('code 2');
  expect(html).toContain('failure details');
  expect(html).toContain('Cette exécution a échoué');
});
it('does not mark a restored execution without WS state as still running or successful', () => {
  useProjectRunStore.setState({ launches: { [projectRunKey(run)]: { runId: 'unknown', pending: false } } });
  const html = renderToStaticMarkup(<PythonConsole run={run} />);
  expect(html).toContain('Résultat non disponible');
  expect(html).not.toContain('Exécution en cours');
  expect(html).not.toContain('code 0');
});
