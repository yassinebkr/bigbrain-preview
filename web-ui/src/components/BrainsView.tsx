// BrainsView — sub-brain states and their events as a dedicated tab,
// separated from the workspace. Top: the live status dots per brain
// (BrainStatusPanel). Below: the recent bus activity feed (task /
// subtask / brain events), newest first — what happened, from whom,
// when.

import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import {
  ChevronDown, ChevronUp, FileCheck2, ScrollText,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { BrainStatusPanel } from './BrainStatusPanel';

interface EvidenceRun {
  run_id: string;
  status: string;
  verdict: string;
  created_at: string;
  name: string;
  user_request: string | null;
  contracts: string[];
  stages: { name: string; status: string }[];
  attempt?: number | null;
  replay_of?: string | null;
  brain?: string | null;
}

const VERDICT_COLORS: Record<string, string> = {
  passed: 'var(--success, #34c759)',
  failed: 'var(--warning, #ff9500)',
  inconclusive: 'var(--text-tertiary)',
};

const FEED_EVENTS = new Set([
  'task.received', 'task.complete', 'task.failed', 'task.cancelled',
  'subtask.started', 'subtask.complete', 'subtask.failed',
  'brain.started', 'brain.complete', 'brain_status',
  'verification.run_recorded',
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

        <EvidenceSection />
      </div>
    </motion.div>
  );
}

// ── Evidence — recorded runs from the deterministic gate ────────────────

function EvidenceSection() {
  const [runs, setRuns] = useState<EvidenceRun[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/evidence/runs?limit=15')
      .then((r) => (r.ok ? r.json() : { runs: [] }))
      .then((d) => { if (!cancelled) setRuns(d.runs || []); })
      .catch(() => { if (!cancelled) setRuns([]); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-surface)' }}
    >
      <h3
        className="text-[12px] font-medium uppercase tracking-wide mb-2"
        style={{ color: 'var(--text-tertiary)' }}
      >
        Evidence — recorded runs
      </h3>

      {runs === null ? (
        <p className="text-[12.5px] py-2" style={{ color: 'var(--text-tertiary)' }}>
          Loading…
        </p>
      ) : runs.length === 0 ? (
        <p className="text-[12.5px] py-2" style={{ color: 'var(--text-tertiary)' }}>
          No recorded runs yet — every agent or manual run leaves an immutable manifest here.
        </p>
      ) : (
        <div className="flex flex-col gap-1">
          {runs.map((run) => {
            const open = openId === run.run_id;
            const verdictColor = VERDICT_COLORS[run.verdict] || 'var(--text-tertiary)';
            return (
              <div key={run.run_id}>
                <button
                  onClick={() => setOpenId(open ? null : run.run_id)}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-left"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <span
                    aria-hidden
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: verdictColor }}
                  />
                  <span className="text-[12.5px] truncate flex-1 min-w-0" style={{ color: 'var(--text-primary)' }}>
                    {run.name}
                  </span>
                  {run.replay_of && (
                    <span className="text-[10px] flex-shrink-0" style={{ color: 'var(--accent-blue)' }}>
                      replay
                    </span>
                  )}
                  <span className="text-[11px] flex-shrink-0" style={{ color: verdictColor }}>
                    {run.verdict}
                  </span>
                  {open
                    ? <ChevronUp size={12} className="flex-shrink-0" />
                    : <ChevronDown size={12} className="flex-shrink-0" />}
                </button>

                {open && (
                  <div className="px-3 py-2 mb-1 rounded-lg" style={{ backgroundColor: 'var(--bg-primary)' }}>
                    {/* Contracts — what the gate checked, stated plainly */}
                    <div className="mb-2">
                      <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wide mb-1" style={{ color: 'var(--text-tertiary)' }}>
                        <ScrollText size={11} /> Contracts
                      </div>
                      {run.contracts.length === 0 ? (
                        <p className="text-[11.5px]" style={{ color: 'var(--text-tertiary)' }}>
                          none — the request named nothing checkable
                        </p>
                      ) : (
                        run.contracts.map((contract, i) => (
                          <div key={i} className="flex items-start gap-1.5 text-[11.5px] mb-0.5">
                            <FileCheck2 size={12} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--accent-blue)' }} />
                            <span style={{ color: 'var(--text-secondary)' }}>{contract}</span>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Stage pills */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {run.stages.map((stage) => {
                        const color =
                          stage.status === 'passed' ? 'var(--success, #34c759)'
                          : stage.status === 'failed' || stage.status === 'inconclusive'
                            ? 'var(--warning, #ff9500)'
                            : 'var(--text-tertiary)';
                        return (
                          <span
                            key={stage.name}
                            className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10.5px]"
                            style={{ color, border: `1px solid ${color}` }}
                          >
                            <span aria-hidden className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
                            {stage.name}
                          </span>
                        );
                      })}
                    </div>

                    <p className="text-[10.5px] mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
                      {run.run_id}{run.brain ? ` · ${run.brain}` : ''}
                      {run.attempt ? ` · attempt ${run.attempt}` : ''}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
