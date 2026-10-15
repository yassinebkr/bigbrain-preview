// AgentActivityStrip — live view of what the system is doing.
// Shows which sub-brain works and on what, without changing the layout:
// a compact pill strip under the messages that appears while a run is in
// flight and fades out a few seconds after the last event.

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, CheckCircle2, XCircle, FileEdit, Brain } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

const IDLE_HIDE_MS = 4000;

const BRAIN_EVENTS: Record<string, { icon: typeof Brain; label: (d: any) => string; done?: 'ok' | 'fail' }> = {
  'subtask.started': {
    icon: Loader2,
    label: (d) => `${d.brain || 'brain'} — ${(d.description || 'working…').slice(0, 60)}`,
  },
  'brain.started': {
    icon: Loader2,
    label: (d) => `${d.brain || d.name || 'brain'} — working`,
  },
  'subtask.complete': {
    icon: CheckCircle2,
    label: (d) => `subtask done (${(d.execution_time || 0).toFixed(1)}s)`,
    done: 'ok',
  },
  'subtask.failed': {
    icon: XCircle,
    label: () => 'subtask failed',
    done: 'fail',
  },
  'task.received': {
    icon: Brain,
    label: (d) => `planning — ${(d.description || '').slice(0, 50)}`,
  },
  'task.complete': {
    icon: CheckCircle2,
    label: () => 'task complete',
    done: 'ok',
  },
  'task.failed': {
    icon: XCircle,
    label: (d) => `task failed${d.error ? ` — ${String(d.error).slice(0, 60)}` : ''}`,
    done: 'fail',
  },
  'workspace.file_written': {
    icon: FileEdit,
    label: (d) => `wrote ${d.path || 'a file'}`,
    done: 'ok',
  },
};

export function AgentActivityStrip() {
  const activities = useAppStore((s) => s.agentActivities);
  const isStreaming = useAppStore((s) => s.isStreaming);
  const [visible, setVisible] = useState(false);

  const last = activities.length ? activities[activities.length - 1] : null;
  const lastTs = last?.ts || 0;

  useEffect(() => {
    if (!lastTs) return;
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), IDLE_HIDE_MS);
    return () => clearTimeout(timer);
  }, [lastTs]);

  // Recent run events, latest first, max 2.
  const recent = activities
    .filter((a) => BRAIN_EVENTS[a.type])
    .slice(-2)
    .reverse();

  const show = (isStreaming || visible) && recent.length > 0;

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 6 }}
          transition={{ duration: 0.25, ease: [0, 0, 0.2, 1] }}
          className="px-4 md:px-10 pb-1.5 flex-shrink-0"
        >
          <div className="max-w-[1200px] mx-auto flex flex-col gap-1">
            {recent.map((activity, i) => {
              const spec = BRAIN_EVENTS[activity.type];
              const Icon = spec.icon;
              const color =
                spec.done === 'fail' ? 'var(--warning, #ff9500)'
                : spec.done === 'ok' ? 'var(--success, #34c759)'
                : 'var(--text-tertiary)';
              return (
                <div
                  key={`${activity.ts}-${activity.type}`}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px]"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-secondary)',
                    opacity: i === 0 ? 1 : 0.65,
                  }}
                >
                  <Icon
                    size={12}
                    className={activity.type.includes('started') || activity.type === 'subtask.started' ? 'animate-spin' : ''}
                    style={{ color, flexShrink: 0 }}
                  />
                  <span className="truncate">{spec.label(activity.detail || {})}</span>
                </div>
              );
            })}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
