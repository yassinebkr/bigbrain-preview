// Proactive nudges — derived PURELY from real state (run results,
// verification verdicts, files written). No timers, no invented data:
// if there is nothing real to suggest, there is no nudge.

import type { RunState } from '@/store/appStore';

export interface Nudge {
  key: string;           // deterministic — dismissal is keyed on it
  message: string;
  actionLabel: string;
  action: 'open_run' | 'view_evidence' | 'open_file';
  file?: string;
}

interface NudgeInputs {
  run: RunState | null;
  viewerFilePath: string | null;
}

export function deriveNudge({ run, viewerFilePath }: NudgeInputs): Nudge | null {
  if (!run) return null;

  if (run.status === 'failed') {
    return {
      key: `run-failed-${run.id}`,
      message: run.error
        ? `Run failed: ${run.error.slice(0, 120)}`
        : 'The last run failed.',
      actionLabel: 'See details',
      action: 'open_run',
    };
  }

  if (run.verification && run.verification.verdict !== 'passed') {
    const verdict = run.verification.verdict === 'failed'
      ? 'the verification gate failed'
      : 'the result is not fully verified';
    return {
      key: `run-verdict-${run.id}-${run.verification.verdict}`,
      message: `The last run completed, but ${verdict}.`,
      actionLabel: 'View evidence',
      action: 'view_evidence',
    };
  }

  if (run.status === 'done' && run.files.length > 0) {
    const last = run.files[run.files.length - 1].path;
    if (viewerFilePath !== last) {
      return {
        key: `run-file-${run.id}-${last}`,
        message: `The agent wrote ${last}.`,
        actionLabel: 'Open file',
        action: 'open_file',
        file: last,
      };
    }
  }

  return null;
}
