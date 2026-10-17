// RunPanel — live view of the current orchestrated run (v2 of the
// activity pills). Visibility derives from RUN STATE, not from a
// per-event timer: while a run is in flight the panel is always visible
// (the old pills blinked on/off every few seconds between sparse
// events). After the run finishes the summary STAYS (it is the record
// of what happened — steps, files) until the user closes it or a new
// run starts.
//
// Collapsed: one compact row (status, description, progress, files).
// Expanded: the plan — subtask steps with their brain and duration,
// files written (clickable: opens the code viewer), errors, and a
// nudge when files landed in sandbox/ with no project selected.

import { useEffect } from 'react';
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
  Ban,
  X,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import type { RunVerification } from '@/store/appStore';

function StatusIcon({ status, size = 13 }: { status: string; size?: number }) {
  if (status === 'running') return <Loader2 size={size} className="animate-spin flex-shrink-0" />;
  if (status === 'done') return <CheckCircle2 size={size} className="flex-shrink-0" />;
  if (status === 'cancelled') return <Ban size={size} className="flex-shrink-0" />;
  return <XCircle size={size} className="flex-shrink-0" />;
}

const statusColor = (status: string) =>
  status === 'running' ? 'var(--text-tertiary)'
  : status === 'done' ? 'var(--success, #34c759)'
  : status === 'cancelled' ? 'var(--text-tertiary)'
  : 'var(--warning, #ff9500)';

// Harness P4 — the gate's verdict, shown as console-style stage pills.
const STAGE_COLORS: Record<string, string> = {
  passed: 'var(--success, #34c759)',
  failed: 'var(--warning, #ff9500)',
  inconclusive: 'var(--warning, #ff9500)',
  not_applicable: 'var(--text-tertiary)',
  skipped: 'var(--text-tertiary)',
  pending: 'var(--text-tertiary)',
  running: 'var(--text-tertiary)',
};

function VerificationChip({ verification }: { verification: RunVerification }) {
  const label =
    verification.verdict === 'passed' ? 'verified'
    : verification.verdict === 'failed' ? 'gate failed'
    : 'unverified';
  const color =
    verification.verdict === 'passed' ? 'var(--success, #34c759)'
    : verification.verdict === 'failed' ? 'var(--warning, #ff9500)'
    : 'var(--text-tertiary)';
  const Icon = verification.verdict === 'passed' ? CheckCircle2 : XCircle;
  return (
    <span className="flex items-center gap-1 flex-shrink-0" style={{ color }}>
      <Icon size={11} />
      <span>{label}</span>
      {verification.attempt != null && verification.attempt > 1 && (
        <span style={{ color: 'var(--text-tertiary)' }}>· try {verification.attempt}</span>
      )}
    </span>
  );
}

function VerificationSection({ verification }: { verification: RunVerification }) {
  return (
    <div className="mt-2 flex items-center gap-1.5 flex-wrap">
      <span
        className="text-[10px] uppercase tracking-wide flex-shrink-0"
        style={{ color: 'var(--text-tertiary)' }}
      >
        verification
      </span>
      {verification.stages.map((stage) => (
        <span
          key={stage.name}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10.5px]"
          style={{
            color: STAGE_COLORS[stage.status] || 'var(--text-tertiary)',
            border: `1px solid ${STAGE_COLORS[stage.status] || 'var(--border-subtle)'}`,
          }}
          title={`stage ${stage.name}: ${stage.status}`}
        >
          <span
            aria-hidden
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: STAGE_COLORS[stage.status] || 'var(--text-tertiary)' }}
          />
          {stage.name}
        </span>
      ))}
    </div>
  );
}

export function RunPanel() {
  const run = useAppStore((s) => s.activeRun);
  const expanded = useAppStore((s) => s.runPanelOpen);
  const setExpanded = useAppStore((s) => s.setRunPanelOpen);
  const dismissed = useAppStore((s) => s.runPanelDismissed);
  const setDismissed = useAppStore((s) => s.setRunPanelDismissed);
  const setView = useAppStore((s) => s.setView);
  const currentProject = useAppStore((s) => s.currentProject);
  const setCurrentProject = useAppStore((s) => s.setCurrentProject);
  const openFileViewer = useAppStore((s) => s.openFileViewer);

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
        : run.status === 'cancelled'
          ? 'Run cancelled'
          : run.error ? `Run failed — ${run.error}` : 'Run failed';

  const sandboxNudge =
    currentProject === null && run.files.some((f) => f.path.startsWith('sandbox/'));

  const openFile = (path: string) => {
    openFileViewer(path);
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
        <div className="max-w-[720px] mx-auto">
          {/* Collapsed row — always one stable height, no re-layout.
              Width matches the chat input, not the full message column. */}
          <div
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
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
            {run.verification && <VerificationChip verification={run.verification} />}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            <button
              onClick={(e) => {
                e.stopPropagation();
                // Closing the record = the user has SEEN this run's
                // outcome: the derived reminders (failed / verdict /
                // written file) must not pop back in its place.
                const dismissNudge = useAppStore.getState().dismissNudge;
                dismissNudge(`run-failed-${run.id}`);
                dismissNudge(`run-verdict-${run.id}-failed`);
                dismissNudge(`run-verdict-${run.id}-inconclusive`);
                const last = run.files.length > 0
                  ? run.files[run.files.length - 1].path : null;
                if (last) dismissNudge(`run-file-${run.id}-${last}`);
                setDismissed(true);
              }}
              className="p-0.5 rounded-md cursor-pointer flex-shrink-0"
              style={{ color: 'var(--text-tertiary)' }}
              aria-label="Dismiss"
              title="Close"
            >
              <X size={12} />
            </button>
          </div>

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
                        <div key={step.id} className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-2 text-[11.5px]">
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
                          {/* Live output — what the brain's program is
                              printing RIGHT NOW (execution.output). */}
                          {step.liveOutput && (
                            <pre
                              className="ml-[23px] mr-2 max-h-[84px] overflow-hidden px-2 py-1 rounded-md text-[10.5px] leading-snug whitespace-pre-wrap"
                              style={{
                                color: 'var(--text-tertiary)',
                                backgroundColor: 'var(--bg-primary)',
                                fontFamily: 'var(--font-mono, monospace)',
                              }}
                            >
                              {step.liveOutput}
                            </pre>
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
                          title="View code"
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

                  {/* Verification — harness gate pills (agent-console style) */}
                  {run.verification && (
                    <VerificationSection verification={run.verification} />
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
