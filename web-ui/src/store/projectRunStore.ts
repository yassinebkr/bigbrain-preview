import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useAppStore, type RunState } from './appStore';
import { isBoardRun } from '@/lib/morphable';

export const projectRunKey = (run: RunState) => JSON.stringify([run.sessionId, run.id]);
export function pythonEntry(run: RunState) {
  if (run.localProject) return undefined;
  if (run.deliveryStatus === 'incomplete' || isBoardRun(run) || run.status !== 'done' || !run.runnable || run.deliverableType === 'web_app') return undefined;
  const path = run.projectPath && run.entryPoint ? `${run.projectPath}/${run.entryPoint}`
    : run.files.find((file) => file.path === run.entryPoint || file.path.endsWith(`/${run.entryPoint}`))?.path;
  return path?.endsWith('.py') ? path : undefined;
}
interface Launch { runId?: string; pending: boolean; awaitingEvents?: boolean; error?: string }
interface ProjectRuns {
  launches: Record<string, Launch>;
  forgetSession: (sessionId: string) => void;
  launch: (run: RunState) => Promise<void>;
}

// Execution correlation, separate from workspace layout preferences. A page
// reload never re-executes code and never claims that a missing WS result passed.
export const useProjectRunStore = create<ProjectRuns>()(persist((set, get) => ({
  launches: {},
  forgetSession: (sessionId) => set((state) => ({ launches: Object.fromEntries(
    Object.entries(state.launches).filter(([key]) => { try { return JSON.parse(key)[0] !== sessionId; } catch { return true; } })) })),
  launch: async (run) => {
    const path = pythonEntry(run);
    if (!path) return;
    const key = projectRunKey(run);
    const prior = get().launches[key];
    const live = prior?.runId ? useAppStore.getState().liveRuns[prior.runId] : undefined;
    if (prior?.pending || (live && !live.done) || (prior?.awaitingEvents && !live)) return;
    set((state) => ({ launches: { ...state.launches, [key]: { pending: true } } }));
    try {
      const response = await fetch('/api/fs/run', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
      const body = await response.json();
      if (!response.ok || typeof body.runId !== 'string') throw new Error(body.error || `Lancement impossible (HTTP ${response.status})`);
      set((state) => ({ launches: { ...state.launches, [key]: { runId: body.runId, pending: false, awaitingEvents: true } } }));
    } catch (error) {
      set((state) => ({ launches: { ...state.launches, [key]: { pending: false, error: String(error) } } }));
    }
  },
}), { name: 'aplot-project-runs-v1', partialize: (state) => ({ launches: Object.fromEntries(
  Object.entries(state.launches).slice(-30).map(([key, launch]) => [key, { ...launch, pending: false, awaitingEvents: false,
    ...(launch.pending ? { error: 'La page a été rechargée pendant le lancement. Son résultat est inconnu.' } : {}) }])) }) }));
