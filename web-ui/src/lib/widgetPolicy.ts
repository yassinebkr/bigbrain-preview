import type { RunState } from '@/store/appStore';
import { isBoardRun, webEntryPath } from './morphable';

export type WidgetKind = 'files' | 'verification' | 'console' | 'preview';
export interface WidgetProposal { version: 1; revision: number; widgets: WidgetKind[] }
const catalog = new Set(['files', 'verification', 'console', 'preview']);

export function parseWidgetProposal(value: unknown): WidgetProposal | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return;
  const p = value as Record<string, unknown>;
  if (Object.keys(p).some((key) => !['version', 'revision', 'widgets'].includes(key)) || p.version !== 1
      || !Number.isSafeInteger(p.revision) || (p.revision as number) < 1 || !Array.isArray(p.widgets)
      || p.widgets.length < 1 || p.widgets.length > 2
      || p.widgets.some((kind) => typeof kind !== 'string' || !catalog.has(kind))
      || new Set(p.widgets).size !== p.widgets.length) return;
  return { version: 1, revision: p.revision as number, widgets: [...p.widgets] as WidgetKind[] };
}

export function composeWidgets(run: RunState, requested?: WidgetKind[], consoleOpen = false): WidgetKind[] {
  const available: WidgetKind[] = [];
  if (!isBoardRun(run)) {
    if (run.files.length) available.push('files');
    const entry = run.projectPath && run.entryPoint ? `${run.projectPath}/${run.entryPoint}`
      : run.files.find((file) => file.path === run.entryPoint || file.path.endsWith(`/${run.entryPoint}`))?.path;
    if (run.status === 'done' && run.runnable && run.deliverableType !== 'web_app'
      && entry?.endsWith('.py')) available.push('console');
    if (webEntryPath(run)) available.push('preview');
  }
  if (run.verification) available.push('verification');
  const mandatory: WidgetKind[] = [];
  // A live console and non-passing evidence cannot be hidden by a suggestion.
  if (consoleOpen && available.includes('console')) mandatory.push('console');
  if (run.verification && run.verification.verdict !== 'passed') mandatory.push('verification');
  const defaults: WidgetKind[] = ['console', 'verification'];
  return [...new Set([...mandatory, ...(Array.isArray(requested) ? requested : defaults)])]
    .filter((kind) => available.includes(kind)).slice(0, 2);
}
