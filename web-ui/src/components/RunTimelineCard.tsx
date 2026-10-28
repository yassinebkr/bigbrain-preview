import { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2, XCircle, Ban, ChevronDown, ChevronUp, FileEdit,
  FolderOpen, Play, Loader2, ListTodo, CircleAlert,
} from 'lucide-react';
import { useAppStore, type RunState } from '@/store/appStore';
import { runTitle, webEntryPath } from '@/lib/morphable';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { pythonEntry, useProjectRunStore } from '@/store/projectRunStore';
import { isPartialResearch } from '@/lib/research';

export function RunTimelineCard({ run }: { run: RunState }) {
  const partialResearch = isPartialResearch(run);
  const [open, setOpen] = useState(false);
  const inspect = useWorkspaceStore((s) => s.inspect);
  const onInspect = () => inspect(run);
  const openFileViewer = useAppStore((s) => s.openFileViewer);
  const setView = useAppStore((s) => s.setView);
  const setPendingOpenFile = useAppStore((s) => s.setPendingOpenFile);
  const setCurrentProject = useAppStore((s) => s.setCurrentProject);
  const [runId, setRunId] = useState<string | null>(null);
  const liveRun = useAppStore((s) => runId ? s.liveRuns[runId] : undefined);
  const outputRef = useRef<HTMLPreElement>(null);
  const isTaskboard = run.resultKind === 'taskboard' || run.steps.some((step) => step.brain === 'taskboard');

  useEffect(() => {
    const el = outputRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [liveRun?.out, liveRun?.err]);
  const entryPath = isTaskboard ? undefined : run.projectPath && run.entryPoint
    ? `${run.projectPath}/${run.entryPoint}`
    : run.entryPoint
      ? run.files.find((file) =>
          file.path === run.entryPoint || file.path.endsWith(`/${run.entryPoint}`))?.path
      : undefined;
  const projectPath = run.projectPath || (entryPath?.includes('/')
    ? entryPath.slice(0, entryPath.lastIndexOf('/')) : undefined);
  const hasPreview = !!webEntryPath(run);
  const canRun = run.deliveryStatus !== 'incomplete' && run.runnable;
  const Icon = run.status === 'done' && run.deliveryStatus !== 'incomplete'
    ? CheckCircle2 : run.status === 'cancelled' ? Ban : partialResearch ? CircleAlert : XCircle;
  const color = run.status === 'done' && run.deliveryStatus !== 'incomplete'
    ? 'var(--success, #34c759)' : 'var(--warning, #ff9500)';

  const openProject = async () => {
    if (!entryPath) return;
    if (projectPath) {
      try {
        const response = await fetch('/api/fs/current-project', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project: projectPath }),
        });
        if (response.ok) setCurrentProject(projectPath);
      } catch { /* workspace can still open the file */ }
    }
    setPendingOpenFile(entryPath);
    setView('workspace');
  };

  const runProject = async () => {
    if (hasPreview) { onInspect(); return; }
    if (pythonEntry(run)) { onInspect(); await useProjectRunStore.getState().launch(run); return; }
    if (!entryPath || (runId && !liveRun?.done)) return;
    setOpen(true);
    try {
      const response = await fetch('/api/fs/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: entryPath }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
      if (body.runId) setRunId(body.runId);
    } catch {
      setRunId(null);
    }
  };

  return (
    <div className="flex justify-start w-full">
      <div
        className="ml-9 min-w-0 flex-1 max-w-[720px] rounded-xl px-3 py-2 text-[12px]"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
      >
        <div
          className="w-full flex items-center gap-2 cursor-pointer"
          onClick={() => setOpen(!open)}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setOpen(!open); }}
          role="button"
          tabIndex={0}
          aria-expanded={open}
        >
          <Icon size={13} style={{ color }} className="flex-shrink-0" />
          <span className="truncate flex-1 text-left" style={{ color: 'var(--text-secondary)' }}>
            {run.deliveryStatus === 'incomplete' ? 'Projet incomplet · non validé' : partialResearch ? 'Recherche incomplète' : run.status === 'done' ? 'Run complete' : run.status === 'cancelled' ? 'Run cancelled' : 'Run failed'}
            {' — '}{runTitle(run)}
          </span>
          {run.files.length > 0 && (
            <span style={{ color: 'var(--text-tertiary)' }}>
              {run.files.length} file{run.files.length > 1 ? 's' : ''}
            </span>
          )}
          {entryPath && (
            <div className="flex items-center gap-1 flex-shrink-0">
              <button onClick={(event) => { event.stopPropagation(); void openProject(); }}
                className="p-1 rounded-md cursor-pointer" style={{ color: 'var(--accent-blue)' }}
                title="Open project" aria-label="Open project">
                <FolderOpen size={12} />
              </button>
              {canRun && !hasPreview && (
                <button onClick={(event) => { event.stopPropagation(); void runProject(); }}
                  disabled={!!runId && !liveRun?.done} className="p-1 rounded-md cursor-pointer"
                  style={{ color: 'var(--accent-blue)' }} title="Run project" aria-label="Run project">
                  {runId && !liveRun?.done ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                </button>
              )}
            </div>
          )}
          {isTaskboard && run.status === 'done' && (
            <button onClick={(event) => { event.stopPropagation(); setView('tasks'); }}
              className="flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer"
              style={{ color: 'var(--accent-blue)' }} aria-label="Open taskboard">
              <ListTodo size={12} /> Taskboard
            </button>
          )}
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </div>
        {run.error && (
          <div className="mt-2 whitespace-pre-wrap break-words" role="alert"
            style={{ color: 'var(--warning, #ff9500)' }}>{partialResearch ? 'Des points restent à établir. Les preuves et les limites sont conservées dans l’Atelier.' : run.error}</div>
        )}
        {!isTaskboard && <button onClick={onInspect} className="mt-2 text-[12px] inline-flex items-center gap-2 py-1" style={{ color: 'var(--accent-blue)' }}>
          {hasPreview ? <><Play size={12} /> Afficher le résultat</> : 'Voir les détails'}
        </button>}
        {open && (
          <div className="mt-2 pt-2 space-y-1.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            {run.steps.map((step) => (
              <div key={step.id} className="flex items-center gap-2" style={{ color: 'var(--text-tertiary)' }}>
                <span>{step.status === 'done' ? '✓' : step.status === 'failed' ? '×' : '•'}</span>
                {step.brain && <span style={{ color: 'var(--accent-blue)' }}>{step.brain}</span>}
                <span className="truncate">{step.description}</span>
              </div>
            ))}
            {run.files.map((file) => (
              <button
                key={file.path}
                onClick={() => openFileViewer(file.path)}
                className="flex items-center gap-2 cursor-pointer"
                style={{ color: 'var(--accent-blue)' }}
              >
                <FileEdit size={11} />
                <span>{file.path}</span>
              </button>
            ))}
            {entryPath && (
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={openProject}
                  className="flex items-center gap-1.5 px-2 py-1 rounded-md cursor-pointer"
                  style={{ color: 'var(--accent-blue)', border: '1px solid var(--border-subtle)' }}
                >
                  <FolderOpen size={11} /> Open project
                </button>
                {canRun && !hasPreview && (
                  <button
                    onClick={runProject}
                    disabled={!!runId && !liveRun?.done}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-md cursor-pointer"
                    style={{ color: '#fff', backgroundColor: 'var(--accent-blue)' }}
                  >
                    {runId && !liveRun?.done
                      ? <Loader2 size={11} className="animate-spin" />
                      : <Play size={11} />}
                    Run project
                  </button>
                )}
              </div>
            )}
            {run.projectName && (!entryPath || !run.runnable) && !run.error && (
              <div style={{ color: 'var(--warning, #ff9500)' }}>
                {run.status === 'failed'
                  ? 'La validation du projet a échoué. Consulte les étapes ci-dessus.'
                  : 'Le lancement de ce projet n’a pas été validé.'}
              </div>
            )}
            {liveRun && (liveRun.out || liveRun.err || liveRun.done) && (
              <pre
                ref={outputRef}
                className="max-h-[180px] overflow-auto rounded-md px-2 py-1.5 whitespace-pre-wrap"
                style={{ backgroundColor: 'var(--bg-primary)', color: liveRun.err
                  ? 'var(--warning, #ff9500)' : 'var(--text-primary)' }}
              >
                {liveRun.out}{liveRun.err}
                {liveRun.done && !liveRun.out && !liveRun.err ? '(no output)' : ''}
              </pre>
            )}
            {run.verification && (
              <div style={{ color: 'var(--text-tertiary)' }}>
                {run.deliveryStatus === 'incomplete' ? 'Livraison non validée · contrôles enregistrés : ' : 'Verification: '}{run.verification.verdict}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
