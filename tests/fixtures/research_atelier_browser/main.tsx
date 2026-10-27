import { createRoot } from 'react-dom/client';
import { ContextWorkspace } from '@/components/ContextWorkspace';
import { useAppStore } from '@/store/appStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import '@/index.css';

function clear() {
  useAppStore.setState({ activeSessionKey: 'audit-chat', activeRun: null, sessionRuns: {},
    runsById: {}, completedRuns: [], sessionProposals: {} });
  useWorkspaceStore.setState({ sessions: {} });
}
clear();
(window as any).audit = {
  replay(frames: any[], reset = true) {
    if (reset) clear();
    for (const frame of frames) useAppStore.getState().applyRunEvent(frame);
  },
  switchTo: (id: string) => useAppStore.getState().switchSession(id),
  state: () => ({ session: useAppStore.getState().activeSessionKey,
    live: Object.keys(useAppStore.getState().runsById), completed: useAppStore.getState().completedRuns.length }),
};
createRoot(document.getElementById('root')!).render(
  <main style={{ height: '100vh', padding: 16 }}>
    <ContextWorkspace>{() => <section>Offline production Atelier acceptance</section>}</ContextWorkspace>
  </main>
);
