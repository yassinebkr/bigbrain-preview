// RunPanel — live view of the current orchestrated run (v2 of the
// activity pills). Visibility derives from RUN STATE, not from a
// per-event timer: while a run is in flight the panel is always visible
// (the old pills blinked on/off every few seconds between sparse
// events); after the run finishes the collapsed summary lingers a few
// seconds, unless the user expanded it.
//
// Collapsed: one compact row (status, description, progress, files).
// Expanded: the plan — subtask steps with their brain and duration,
// files written (clickable: jumps to the workspace viewer), errors,
// and a nudge when files landed in sandbox/ with no project selected.

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Loader2,
  CheckCircle2,
  XCircle,
  FileEdit,
  ChevronDown,
  ChevronUp,
  FolderOpen,
  AlertTriangle,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';

const LINGER_MS = 12_000;

function StatusIcon({ status, size = 13 }: { status: string; size?: number }) {
  if (status === 'running') return <Loader2 size={size} className="animate-spin flex-shrink-0" />;
  if (status === 'done') return <CheckCircle2 size={size} className="flex-shrink-0" />;
  return <XCircle size={size} className="flex-shrink-0" />;
}

const statusColor = (status: string) =>
  status === 'running' ? 'var(--text-tertiary)'
  : status === 'done' ? 'var(--success, #34c759)'
  : 'var(--warning, #ff9500)';

export function RunPanel() {
  const run = useAppStore((s) => s.activeRun);
  const expanded = useAppStore((s) => s.runPanelOpen);
  const setExpanded = useAppStore((s) => s.setRunPanelOpen);
  const setView = useAppStore((s) => s.setView);
  const currentProject = useAppStore((s) => s.currentProject);
  const setCurrentProject = useAppStore((s) => s.setCurrentProject);
  const setPendingOpenFile = useAppStore((s) => s.setPendingOpenFile);
  const [dismissed, setDismissed] = useState(false);

  // The store's project mirror is only filled by the file explorer; when a
  // run writes into sandbox/, fetch the authoritative value once so the
  // nudge does not show for users who did select a project.
  useEffect(() => {
    if (!run || currentProject !== null) return;
    if (!run.files.some((f) => f.path.startsWith('sandbox/'))) return;
    fetch('/api/fs/current-project')
      .then((r) => r.json())
      .then((d) => setCurrentProject(d.project || null))
      .catch(() => { /* keep the mirror null */ });
  }, [run?.id, run?.files.length, currentProject, setCurrentProject]);

  // A new run always shows (reset any dismissal of the previous summary).
  useEffect(() => {
    if (run) setDismissed(false);
  }, [run?.id]);

  // Once the run finishes (and is not expanded), hide the summary later.
  useEffect(() => {
    if (!run || run.status === 'running' || expanded) return;
    const timer = setTimeout(() => setDismissed(true), LINGER_MS);
    return () => clearTimeout(timer);
  }, [run?.status, run?.finishedAt, expanded]);

  if (!run || dismissed) return null;

  const stepsDone = run.steps.filter((s) => s.status !== 'running').length;
  const running = run.steps.find((s) => s.status === 'running');
  const summary =
    run.status === 'running'
      ? running
        ? `${running.brain || 'brain'} — ${running.description}`
        : run.description
      : run.status === 'done'
        ? 'Run complete'
        : run.error ? `Run failed — ${run.error}` : 'Run failed';

  const sandboxNudge =
    currentProject === null && run.files.some((f) => f.path.startsWith('sandbox/'));

  const openFile = (path: string) => {
    setPendingOpenFile(path);
    setView('workspace');
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 6 }}
        transition={{ duration: 0.25, ease: [0, 0, 0.2, 1] }}
        className="px-4 md:px-10 pb-1.5 flex-shrink-0"
      >
        <div className="max-w-[1200px] mx-auto">
          {/* Collapsed row — always one stable height, no re-layout */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              textAlign: 'left',
            }}
          >
            <span style={{ color: statusColor(run.status) }}>
              <StatusIcon status={run.status} />
            </span>
            <span className="truncate flex-1 min-w-0">{summary}</span>
            {run.steps.length > 0 && (
              <span className="flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                {stepsDone}/{run.steps.length}
              </span>
            )}
            {run.files.length > 0 && (
              <span className="flex items-center gap-1 flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                <FileEdit size={11} /> {run.files.length}
              </span>
            )}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>

          {/* Expanded: the plan */}
          <AnimatePresence initial={false}>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: [0, 0, 0.2, 1] }}
                className="overflow-hidden"
              >
                <div
                  className="mt-1 rounded-lg px-3 py-2.5 max-h-[40vh] overflow-y-auto"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span style={{ color: statusColor(run.status) }}>
                      <StatusIcon status={run.status} size={12} />
                    </span>
                    <span className="text-[12.5px] font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                      {run.description}
                    </span>
                  </div>

                  {/* Steps */}
                  {run.steps.length > 0 && (
                    <div className="flex flex-col gap-1">
                      {run.steps.map((step) => (
                        <div key={step.id} className="flex items-center gap-2 text-[11.5px]">
                          <span style={{ color: statusColor(step.status) }}>
                            <StatusIcon status={step.status} size={11} />
                          </span>
                          {step.brain && (
                            <span
                              className="flex-shrink-0 px-1.5 py-px rounded"
                              style={{ color: 'var(--accent-blue)', border: '1px solid var(--border-subtle)' }}
                            >
                              {step.brain}
                            </span>
                          )}
                          <span className="truncate flex-1 min-w-0" style={{ color: 'var(--text-secondary)' }}>
                            {step.description}
                          </span>
                          {step.durationMs != null && step.status !== 'running' && (
                            <span className="flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                              {(step.durationMs / 1000).toFixed(1)}s
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Files written — click opens them in the workspace viewer */}
                  {run.files.length > 0 && (
                    <div className="mt-2 flex flex-col gap-1">
                      {run.files.map((file) => (
                        <button
                          key={file.path}
                          onClick={() => openFile(file.path)}
                          className="flex items-center gap-2 text-[11.5px] cursor-pointer px-1 py-0.5 rounded hover:brightness-125"
                          style={{ color: 'var(--accent-blue)' }}
                          title="Open in workspace"
                        >
                          <FileEdit size={11} className="flex-shrink-0" />
                          <span className="truncate">{file.path}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Nudge: global mode writes pile into the sandbox project */}
                  {sandboxNudge && (
                    <div
                      className="mt-2 flex items-center gap-2 text-[11.5px] px-2 py-1.5 rounded"
                      style={{ backgroundColor: 'rgba(0, 113, 227, 0.08)', color: 'var(--text-secondary)' }}
                    >
                      <AlertTriangle size={12} className="flex-shrink-0" style={{ color: 'var(--accent-blue)' }} />
                      <span className="flex-1 min-w-0">
                        Files landed in <b>sandbox/</b> — no project selected.
                      </span>
                      <button
                        onClick={() => setView('workspace')}
                        className="flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer flex-shrink-0"
                        style={{ color: 'var(--accent-blue)', border: '1px solid var(--border-subtle)' }}
                      >
                        <FolderOpen size={11} /> Workspace
                      </button>
                    </div>
                  )}

                  {/* Failure detail */}
                  {run.status === 'failed' && run.error && (
                    <div className="mt-2 text-[11.5px]" style={{ color: 'var(--warning, #ff9500)' }}>
                      {run.error}
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
