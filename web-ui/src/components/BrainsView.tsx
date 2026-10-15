// BrainsView — sub-brain states and their events as a dedicated tab,
// separated from the workspace. Top: the live status dots per brain
// (BrainStatusPanel). Below: the recent bus activity feed (task /
// subtask / brain events), newest first — what happened, from whom,
// when.

import { motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { BrainStatusPanel } from './BrainStatusPanel';

const FEED_EVENTS = new Set([
  'task.received', 'task.complete', 'task.failed', 'task.cancelled',
  'subtask.started', 'subtask.complete', 'subtask.failed',
  'brain.started', 'brain.complete', 'brain_status',
]);

function timeOf(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function BrainsView() {
  const activities = useAppStore((s) => s.agentActivities);
  const feed = activities.filter((a) => FEED_EVENTS.has(a.type)).slice(-60).reverse();

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35, ease: [0, 0, 0.2, 1] }}
      className="flex flex-col h-full w-full overflow-y-auto"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="max-w-[1000px] w-full mx-auto px-3 sm:px-4 py-4 flex flex-col gap-4">
        <div
          className="rounded-xl border overflow-hidden max-h-[340px] flex-shrink-0"
          style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-surface)' }}
        >
          <BrainStatusPanel />
        </div>

        <div
          className="rounded-xl border p-3"
          style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-surface)' }}
        >
          <h3
            className="text-[12px] font-medium uppercase tracking-wide mb-2"
            style={{ color: 'var(--text-tertiary)' }}
          >
            Activity
          </h3>
          {feed.length === 0 ? (
            <p className="text-[12.5px] py-4" style={{ color: 'var(--text-tertiary)' }}>
              No brain activity yet — send a task in the chat.
            </p>
          ) : (
            <div className="flex flex-col gap-1">
              {feed.map((a, i) => (
                <div
                  key={`${a.ts}-${a.type}-${i}`}
                  className="flex items-start gap-2 text-[11.5px] px-1 py-1 rounded"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <span className="flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                    {timeOf(a.ts)}
                  </span>
                  <span
                    className="flex-shrink-0 px-1.5 rounded"
                    style={{ color: 'var(--accent-blue)', border: '1px solid var(--border-subtle)' }}
                  >
                    {a.type}
                  </span>
                  <span className="truncate flex-1 min-w-0" style={{ fontFamily: 'var(--font-mono, monospace)' }}>
                    {a.detail?.brain || a.detail?.description || a.name || ''}
                    {a.detail?.error ? ` — ${String(a.detail.error).slice(0, 80)}` : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
