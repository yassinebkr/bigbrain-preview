// NudgeBar — one contextual, REAL suggestion above the chat input.
// The nudge derives from run state (lib/nudges.ts); a dismissed key
// never reappears. Zero mock: no state-derived nudge = no bar.

import { AnimatePresence, motion } from 'framer-motion';
import { X, Zap } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { deriveNudge } from '@/lib/nudges';

export function NudgeBar() {
  const run = useAppStore((s) => s.activeRun);
  const viewerFilePath = useAppStore((s) => s.viewerFilePath);
  const dismissed = useAppStore((s) => s.dismissedNudges);
  const dismissNudge = useAppStore((s) => s.dismissNudge);
  const openFileViewer = useAppStore((s) => s.openFileViewer);
  const setView = useAppStore((s) => s.setView);
  const setRunPanelOpen = useAppStore((s) => s.setRunPanelOpen);

  const nudge = deriveNudge({ run, viewerFilePath });
  if (!nudge || dismissed.includes(nudge.key)) return null;

  const act = () => {
    if (nudge.action === 'open_run') {
      setRunPanelOpen(true);
    } else if (nudge.action === 'view_evidence') {
      setView('evidence');
    } else if (nudge.action === 'open_file' && nudge.file) {
      openFileViewer(nudge.file);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        className="w-full max-w-[720px] mx-auto flex items-center gap-2 px-3 py-1.5 rounded-lg mb-1.5"
        style={{
          backgroundColor: 'var(--bg-secondary, #1a1a2e)',
          border: '1px solid var(--border-subtle, #2a2a3e)',
        }}
      >
        <Zap size={12} className="flex-shrink-0" style={{ color: 'var(--accent, #7c6ff0)' }} />
        <span
          className="text-[12px] flex-1 min-w-0 truncate"
          style={{ color: 'var(--text-secondary, #ccc)' }}
        >
          {nudge.message}
        </span>
        <button
          onClick={act}
          className="text-[11.5px] font-medium px-2 py-0.5 rounded-md flex-shrink-0"
          style={{
            color: 'var(--accent, #7c6ff0)',
            backgroundColor: 'var(--bg-tertiary, #23233a)',
          }}
        >
          {nudge.actionLabel}
        </button>
        <button
          onClick={() => dismissNudge(nudge.key)}
          className="flex-shrink-0 p-0.5 rounded"
          style={{ color: 'var(--text-tertiary, #888)' }}
          aria-label="Dismiss suggestion"
        >
          <X size={12} />
        </button>
      </motion.div>
    </AnimatePresence>
  );
}
