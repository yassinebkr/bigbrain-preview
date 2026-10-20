import type { RunState } from '@/store/appStore';
import type { WidgetKind } from './widgetPolicy';

export type SurfaceKind = 'preview' | 'activity' | 'files' | 'verification';
export type WorkspaceMode = 'focus' | 'peek' | 'workspace' | 'expanded';
export interface WorkspacePreference {
  mode?: WorkspaceMode;
  selectedId?: string;
  selectedAt?: number; // explicit inspection; new work may follow, old work may not steal it
  width?: number;
  widgetChoices?: Record<string, { revision: number; widgets: WidgetKind[] }>;
}
export interface WorkSurface {
  id: string;
  kind: SurfaceKind;
  run: RunState;
}

export const surfaceId = (run: RunState, kind: SurfaceKind) =>
  `${encodeURIComponent(run.sessionId)}/${encodeURIComponent(run.id)}/${kind}`;

export const isBoardRun = (run: RunState) => run.resultKind === 'taskboard' || run.steps.some((step) => step.brain === 'taskboard');
export function nextProjectAttempt(selected: RunState | undefined, surfaces: WorkSurface[], inspectedAt = 0) {
  if (!selected) return undefined;
  return surfaces.filter((s) => s.kind === 'activity' && !!s.run.projectPath
    && (s.run.projectPath === selected.projectPath || !selected.projectPath && selected.status !== 'running')
    && s.run.sessionId === selected.sessionId && s.run.startedAt > Math.max(selected.startedAt, inspectedAt))
    .sort((a, b) => b.run.startedAt - a.run.startedAt)[0];
}
export function webEntryPath(run: RunState) {
  if (isBoardRun(run) || run.status !== 'done' || !run.runnable || run.deliverableType !== 'web_app') return undefined;
  return run.projectPath && run.entryPoint ? `${run.projectPath}/${run.entryPoint}` : undefined;
}
export function runTitle(run: RunState) {
  const name = run.projectName || run.projectPath?.split('/').pop();
  return name ? name.replaceAll(/[-_]/g, ' ').replace(/^./, (c) => c.toUpperCase()) : run.description;
}

// Closed catalog, real run data only. This is presentation, not intent routing.
export function surfaceRegistry(sessionId: string | null, runs: RunState[]): WorkSurface[] {
  if (!sessionId) return [];
  const unique = new Map<string, RunState>();
  for (const run of runs) if (run.sessionId === sessionId && !unique.has(run.id)) unique.set(run.id, run);
  return [...unique.values()]
    .sort((a, b) => Number(b.status === 'running') - Number(a.status === 'running')
      || (a.status === 'running' ? a.startedAt - b.startedAt : b.startedAt - a.startedAt)
      || a.id.localeCompare(b.id))
    .flatMap((run): WorkSurface[] => [
      ...(webEntryPath(run) ? [{ id: surfaceId(run, 'preview'), kind: 'preview' as const, run }] : []),
      { id: surfaceId(run, 'activity'), kind: 'activity', run },
      ...(run.files.length ? [{ id: surfaceId(run, 'files'), kind: 'files' as const, run }] : []),
      ...(run.verification ? [{ id: surfaceId(run, 'verification'), kind: 'verification' as const, run }] : []),
    ]);
}

export function reconcileWorkspace(surfaces: WorkSurface[], preference: WorkspacePreference = {}) {
  // An explicit choice never silently switches to a different artifact while
  // history is restoring (or when the selected run was pruned).
  const selected = preference.selectedId
    ? surfaces.find((surface) => surface.id === preference.selectedId)
    : surfaces[0];
  const mode = preference.mode && ['focus', 'peek', 'workspace', 'expanded'].includes(preference.mode)
    ? preference.mode : (surfaces.length ? 'peek' : 'focus');
  const width = typeof preference.width === 'number' && Number.isFinite(preference.width) ? preference.width : 400;
  return { mode, selected, width: Math.min(1000, Math.max(400, width)) };
}
