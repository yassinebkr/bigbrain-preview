// EvidenceView — the deterministic harness's audit trail, as its own tab.
// Every agent or manual run leaves an immutable manifest; this view lists
// them (newest first), shows the contracts the gate checked in plain
// language, the stage pills, and the replay chain. Read-only — evidence
// is immutable once terminal; this is what HAPPENED, not what to do.

import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import {
  ChevronDown, ChevronUp, FileCheck2, ScrollText,
} from 'lucide-react';

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

function timeOf(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? ''
    : d.toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export function EvidenceView() {
  const [runs, setRuns] = useState<EvidenceRun[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/evidence/runs?limit=50')
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
        return body;
      })
      .then((d) => { if (!cancelled) setRuns(d.runs || []); })
      .catch((e) => {
        if (!cancelled) {
          setError(String(e.message || e));
          setRuns([]);
        }
      });
    return () => { cancelled = true; };
  }, []);

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
        <div className="flex items-center gap-2">
          <ScrollText size={16} style={{ color: 'var(--accent-blue)' }} />
          <h2 className="text-[15px] font-medium" style={{ color: 'var(--text-primary)' }}>
            Evidence
          </h2>
          <span className="text-[11.5px]" style={{ color: 'var(--text-tertiary)' }}>
            immutable record of every verified run — contracts, stages, verdicts
          </span>
        </div>

        {error && (
          <p className="text-[12.5px]" style={{ color: 'var(--warning, #ff9500)' }}>{error}</p>
        )}

        {runs === null ? (
          <p className="text-[12.5px] py-4" style={{ color: 'var(--text-tertiary)' }}>
            Loading…
          </p>
        ) : runs.length === 0 ? (
          <p className="text-[12.5px] py-4" style={{ color: 'var(--text-tertiary)' }}>
            No recorded runs yet — every agent or manual run leaves a manifest here.
          </p>
        ) : (
          <div
            className="rounded-xl border p-2 flex flex-col gap-1"
            style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-surface)' }}
          >
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
                    <span className="text-[11px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                      {timeOf(run.created_at)}
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
    </motion.div>
  );
}
