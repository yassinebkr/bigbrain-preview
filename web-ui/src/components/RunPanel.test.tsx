import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RunPanel } from './RunPanel';
import { ContractCard } from './ContractCard';
import { useAppStore, type RunState } from '@/store/appStore';

// SSR otherwise reads Zustand's initial snapshot, not the injected test state.
vi.mock('@/store/appStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/appStore')>();
  const hook = Object.assign((selector?: (state: ReturnType<typeof actual.useAppStore.getState>) => unknown) =>
    selector ? selector(actual.useAppStore.getState()) : actual.useAppStore.getState(), actual.useAppStore);
  return { ...actual, useAppStore: hook };
});

describe('architecture preparation feedback', () => {
  const original = useAppStore.getState();
  afterEach(() => useAppStore.setState(original));

  it('shows the explicit project destination in the approval card', () => {
    useAppStore.setState({ contractProposal: {
      planId: 'running', designId: 'design', request: 'Running tracker',
      contracts: ['La progression est conservée'], target: { mode: 'new', path: 'sandbox/running' },
    } });
    const html = renderToStaticMarkup(<ContractCard />);
    expect(html).toContain('Nouveau projet');
    expect(html).toContain('sandbox/running');
    expect(html).not.toContain('blender');
  });

  it.each([false, true])('shows real waiting time with expanded=%s', (expanded) => {
    const run: RunState = {
      id: 'routing-running', sessionId: 'sess-running', description: 'Running tracker',
      status: 'running', startedAt: 1, files: [], steps: [{
        id: 'planning-architect', brain: 'planner', status: 'running',
        description: 'Architecture et critères d’acceptation', durationMs: 15000,
      }],
    };
    useAppStore.setState({
      activeSessionKey: 'sess-running', activeRun: run,
      sessionRuns: { 'sess-running': run }, runPanelOpen: expanded, runPanelDismissed: false,
    });
    const html = renderToStaticMarkup(<RunPanel />);
    expect(html).toContain('Architecture et critères d’acceptation');
    expect(html).toContain('15 s');
    expect(html).not.toContain('100%');
  });
});
