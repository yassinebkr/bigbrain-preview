import { Loader2, ArrowRight } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

// One compact, real-state breadcrumb outside chat; details stay in the conversation.
export function ActivityStrip() {
  const runsById = useAppStore((s) => s.runsById);
  const view = useAppStore((s) => s.view);
  const openSession = useAppStore((s) => s.openSession);
  const setView = useAppStore((s) => s.setView);
  const runs = Object.values(runsById);
  if (view === 'chat' || runs.length === 0) return null;
  const run = runs[0];
  const step = run.steps.find((s) => s.status === 'running');
  return (
    <button className="flex items-center gap-2 px-4 py-1.5 text-[11px] text-left cursor-pointer flex-shrink-0"
      style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}
      aria-label="Return to ongoing activity"
      onClick={() => { openSession(run.sessionId); setView('chat'); }}>
      <Loader2 size={11} className={run.awaitingApproval ? '' : 'animate-spin'} />
      <span className="truncate flex-1">
        {runs.length} activité{runs.length > 1 ? 's' : ''} · {run.awaitingApproval ? 'Contrat à approuver' : step ? `${step.brain || 'agent'} · ${step.description}` : run.description}
      </span>
      <ArrowRight size={11} />
    </button>
  );
}
