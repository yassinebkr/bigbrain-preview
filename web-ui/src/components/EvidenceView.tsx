// EvidenceView — the deterministic harness's audit trail, as its own tab.
// Runs are GROUPED BY TASK (one row per request, attempt history inside)
// — a flat per-attempt list was unreadable. Filters by verdict, live
// search, per-task attempt timeline with stage dots. Read-only: this is
// what HAPPENED, not what to do.

import { motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import {
  ChevronDown, ChevronUp, FileCheck2, ScrollText, Search, RotateCcw,
} from 'lucide-react';

interface EvidenceRun {
  run_id: string;
  status: string;
  verdict: string;
  created_at: string;
  attempt?: number | null;
  replay_of?: string | null;
  brain?: string | null;
  stages: { name: string; status: string }[];
  browser_evidence?: {
    details: { error?: string; cases?: { name: string; status: string; error?: string }[] };
    screenshots: string[];
    report?: string;
  } | null;
}

interface EvidenceTask {
  design_id: string;
  name: string;
  user_request: string | null;
  contracts: string[];
  approval?: { decision: string; by: string; at: string; plan_id: string | null } | null;
  runs: EvidenceRun[];
  total: number;
  passed: number;
  failed: number;
  last_verdict: string;
  last_run_id: string;
  last_at: string;
  has_replay: boolean;
}

const VERDICT_COLORS: Record<string, string> = {
  passed: 'var(--success, #34c759)',
  failed: 'var(--warning, #ff9500)',
  inconclusive: 'var(--text-tertiary)',
};

function timeOf(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function StageDots({ stages }: { stages: { name: string; status: string }[] }) {
  return (
    <span className="flex items-center gap-1 flex-wrap">
      {stages.map((stage) => {
        const color =
          stage.status === 'passed' ? 'var(--success, #34c759)'
          : stage.status === 'failed' || stage.status === 'inconclusive'
            ? 'var(--warning, #ff9500)'
            : 'var(--text-tertiary)';
        return (
          <span
            key={stage.name}
            title={`${stage.name}: ${stage.status}`}
            aria-label={`${stage.name}: ${stage.status}`}
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: color }}
          />
        );
      })}
    </span>
  );
}

type Filter = 'all' | 'passed' | 'failed';

export function EvidenceView() {
  const [tasks, setTasks] = useState<EvidenceTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetch('/api/evidence/runs?limit=200')
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
        return body;
      })
      .then((d) => { if (!cancelled) setTasks(d.tasks || []); })
      .catch((e) => {
        if (!cancelled) {
          setError(String(e.message || e));
          setTasks([]);
        }
      });
    return () => { cancelled = true; };
  }, []);

  const visible = useMemo(() => {
    if (!tasks) return [];
    const q = query.trim().toLowerCase();
    return tasks.filter((t) => {
      if (filter === 'passed' && t.last_verdict !== 'passed') return false;
      if (filter === 'failed' && t.last_verdict !== 'failed') return false;
      if (q && !t.name.toLowerCase().includes(q)
          && !(t.user_request || '').toLowerCase().includes(q)) return false;
      return true;
    });
  }, [tasks, filter, query]);

  const stats = useMemo(() => {
    if (!tasks) return null;
    const runs = tasks.reduce((n, t) => n + t.total, 0);
    const passed = tasks.filter((t) => t.last_verdict === 'passed').length;
    const failed = tasks.filter((t) => t.last_verdict === 'failed').length;
    return { tasks: tasks.length, runs, passed, failed };
  }, [tasks]);

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35, ease: [0, 0, 0.2, 1] }}
      className="flex flex-col h-full w-full overflow-y-auto"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="max-w-[1000px] w-full mx-auto px-3 sm:px-4 py-4 flex flex-col gap-3">
        {/* Header + stats */}
        <div className="flex items-center gap-2 flex-wrap">
          <ScrollText size={16} style={{ color: 'var(--accent-blue)' }} />
          <h2 className="text-[15px] font-medium" style={{ color: 'var(--text-primary)' }}>
            Evidence
          </h2>
          {stats && (
            <span className="text-[11.5px]" style={{ color: 'var(--text-tertiary)' }}>
              {stats.tasks} task{stats.tasks > 1 ? 's' : ''} · {stats.runs} recorded run{stats.runs > 1 ? 's' : ''}
              {' · '}
              <span style={{ color: 'var(--success, #34c759)' }}>
                {stats.passed}/{stats.tasks} passing
              </span>
              {stats.failed > 0 && (
                <>
                  {' · '}
                  <span style={{ color: 'var(--warning, #ff9500)' }}>{stats.failed} failing</span>
                </>
              )}
            </span>
          )}
        </div>

        {/* Filters + search */}
        <div className="flex items-center gap-2 flex-wrap">
          {(['all', 'passed', 'failed'] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="px-2.5 py-1 rounded-full text-[11.5px] cursor-pointer"
              style={{
                color: filter === f ? '#ffffff' : 'var(--text-secondary)',
                backgroundColor: filter === f ? 'var(--accent-blue)' : 'var(--bg-surface)',
                border: `1px solid ${filter === f ? 'var(--accent-blue)' : 'var(--border-subtle)'}`,
              }}
            >
              {f === 'all' ? 'All' : f === 'passed' ? 'Passed' : 'Failed'}
            </button>
          ))}
          <div
            className="flex items-center gap-1.5 px-2 py-1 rounded-lg flex-1 min-w-[160px] max-w-[280px]"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
          >
            <Search size={12} style={{ color: 'var(--text-tertiary)' }} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search tasks…"
              className="flex-1 bg-transparent border-none outline-none text-[12px]"
              style={{ color: 'var(--text-primary)' }}
            />
          </div>
        </div>

        {error && (
          <p className="text-[12.5px]" style={{ color: 'var(--warning, #ff9500)' }}>{error}</p>
        )}

        {/* Task groups */}
        {tasks === null ? (
          <p className="text-[12.5px] py-4" style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
        ) : visible.length === 0 ? (
          <p className="text-[12.5px] py-4" style={{ color: 'var(--text-tertiary)' }}>
            {tasks.length === 0
              ? 'No recorded runs yet — every agent or manual run leaves a manifest here.'
              : 'No task matches this filter.'}
          </p>
        ) : (
          <div
            className="rounded-xl border p-2 flex flex-col gap-1"
            style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-surface)' }}
          >
            {visible.map((task) => {
              const open = openId === task.design_id;
              const verdictColor = VERDICT_COLORS[task.last_verdict] || 'var(--text-tertiary)';
              return (
                <div key={task.design_id}>
                  <button
                    onClick={() => setOpenId(open ? null : task.design_id)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-left"
                  >
                    <span
                      aria-hidden
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: verdictColor }}
                    />
                    <span className="text-[12.5px] truncate flex-1 min-w-0" style={{ color: 'var(--text-primary)' }}>
                      {task.name}
                    </span>
                    {task.total > 1 && (
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0"
                        style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
                        title={`${task.total} recorded attempts`}
                      >
                        ×{task.total}
                      </span>
                    )}
                    {task.has_replay && (
                      <RotateCcw size={11} className="flex-shrink-0" style={{ color: 'var(--accent-blue)' }} />
                    )}
                    <span className="text-[11px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                      {timeOf(task.last_at)}
                    </span>
                    <span className="text-[11px] flex-shrink-0" style={{ color: verdictColor }}>
                      {task.last_verdict}
                    </span>
                    {open
                      ? <ChevronUp size={12} className="flex-shrink-0" />
                      : <ChevronDown size={12} className="flex-shrink-0" />}
                  </button>

                  {open && (
                    <div className="px-3 py-2 mb-1 rounded-lg flex flex-col gap-2"
                         style={{ backgroundColor: 'var(--bg-primary)' }}>
                      {/* Contracts — what the gate checked, stated plainly */}
                      <div>
                        <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wide mb-1"
                             style={{ color: 'var(--text-tertiary)' }}>
                          <ScrollText size={11} /> Contracts
                          {task.approval && (
                            <span
                              className="ml-1 px-1.5 py-0.5 rounded text-[10px] normal-case tracking-normal"
                              style={{
                                color: task.approval.decision === 'approved'
                                  ? 'var(--success, #34c759)'
                                  : 'var(--warning, #ff9500)',
                                border: '1px solid var(--border-subtle)',
                              }}
                            >
                              {task.approval.decision === 'approved' ? 'user approved' : 'user rejected'}
                            </span>
                          )}
                        </div>
                        {task.contracts.length === 0 ? (
                          <p className="text-[11.5px]" style={{ color: 'var(--text-tertiary)' }}>
                            none — the request named nothing checkable
                          </p>
                        ) : (
                          task.contracts.map((contract, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-[11.5px] mb-0.5">
                              <FileCheck2 size={12} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--accent-blue)' }} />
                              <span style={{ color: 'var(--text-secondary)' }}>{contract}</span>
                            </div>
                          ))
                        )}
                      </div>

                      {/* Attempt timeline */}
                      <div>
                        <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wide mb-1"
                             style={{ color: 'var(--text-tertiary)' }}>
                          Runs ({task.total})
                        </div>
                        <div className="flex flex-col gap-0.5">
                          {task.runs.map((run, i) => {
                            const runColor = VERDICT_COLORS[run.verdict] || 'var(--text-tertiary)';
                            return (
                              <div key={run.run_id}>
                              <div
                                   className="flex items-center gap-2 text-[11px] px-1 py-0.5 rounded"
                                   style={{ opacity: i === 0 ? 1 : 0.75 }}>
                                <span className="flex-shrink-0" style={{ color: runColor }}>
                                  {run.replay_of ? <RotateCcw size={10} /> : '●'}
                                </span>
                                <span className="flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                                  {run.replay_of ? 'replay' : `try ${run.attempt ?? '?'}`}
                                </span>
                                <StageDots stages={run.stages} />
                                <span className="flex-1" />
                                <span className="flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                                  {timeOf(run.created_at)}
                                </span>
                                <span className="flex-shrink-0" style={{ color: runColor }}>
                                  {run.verdict}
                                </span>
                              </div>
                              {run.browser_evidence && (
                                <details className="ml-4 my-2 text-[11px]">
                                  <summary className="cursor-pointer" style={{ color: 'var(--accent-blue)' }}>Preuves navigateur</summary>
                                  {run.browser_evidence.details.error && <p className="whitespace-pre-wrap">{run.browser_evidence.details.error}</p>}
                                  {run.browser_evidence.details.cases?.map((scenario, index) => (
                                    <p key={index} className="my-1 whitespace-pre-wrap">{scenario.status === 'passed' ? '✓' : '×'} {scenario.name}{scenario.error ? ` — ${scenario.error}` : ''}</p>
                                  ))}
                                  <div className="flex flex-wrap gap-2 my-2">
                                    {run.browser_evidence.screenshots.map((sha) => (
                                      <a key={sha} href={`/api/evidence/image/${sha}`} target="_blank" rel="noreferrer">
                                        <img src={`/api/evidence/image/${sha}`} alt="Capture réelle de la vérification navigateur" className="w-48 rounded border" loading="lazy" />
                                      </a>
                                    ))}
                                  </div>
                                </details>
                              )}
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      <p className="text-[10.5px]" style={{ color: 'var(--text-tertiary)' }}>
                        {task.last_run_id} · {task.runs[0]?.brain || 'unknown brain'}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </motion.div>
  );
}
