import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { surfaceId, webEntryPath, type WorkspacePreference } from '@/lib/morphable';
import type { RunState } from './appStore';
import { parseWidgetProposal } from '@/lib/widgetPolicy';

interface WorkspaceState {
  sessions: Record<string, WorkspacePreference>;
  forgetSession: (sessionId: string) => void;
  update: (sessionId: string, preference: WorkspacePreference) => void;
  inspect: (run: RunState) => void;
  acceptWidgets: (run: RunState) => void;
  resetWidgets: (run: RunState) => void;
}

// Only user-owned presentation preferences; no copy of execution state.
export const useWorkspaceStore = create<WorkspaceState>()(persist((set) => ({
  sessions: {},
  forgetSession: (sessionId) => set((state) => {
    const sessions = { ...state.sessions }; delete sessions[sessionId]; return { sessions };
  }),
  acceptWidgets: (run) => set((state) => {
    const proposal = parseWidgetProposal(run.widgetProposal);
    if (!proposal) return {};
    const prior = state.sessions[run.sessionId] || {};
    return { sessions: { ...state.sessions, [run.sessionId]: { ...prior,
      widgetChoices: { ...prior.widgetChoices, [run.id]: { revision: proposal.revision, widgets: [...proposal.widgets] } } } } };
  }),
  resetWidgets: (run) => set((state) => {
    const prior = state.sessions[run.sessionId];
    if (!prior) return {};
    const choices = { ...prior.widgetChoices };
    delete choices[run.id];
    return { sessions: { ...state.sessions, [run.sessionId]: { ...prior, widgetChoices: choices } } };
  }),
  inspect: (run) => set((state) => ({ sessions: { ...state.sessions,
    [run.sessionId]: { ...state.sessions[run.sessionId], mode: 'workspace',
      selectedAt: Date.now(),
      selectedId: surfaceId(run, webEntryPath(run) ? 'preview' : 'activity') },
  } })),
  update: (sessionId, preference) => set((state) => ({
    sessions: { ...state.sessions, [sessionId]: { ...state.sessions[sessionId], ...preference } },
  })),
}), { name: 'aplot-workspace-v1', partialize: (state) => ({ sessions: state.sessions }) }));
