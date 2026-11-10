import type { RunState } from '@/store/appStore';

/** Keep the diagnostic attached to the attempt that produced it. */
export function RunAttemptHistory({ run }: { run: RunState }) {
  const attempt = run.previousAttempt;
  if (!attempt) return null;
  return <details className="mt-3 text-[12px]">
    <summary className="work-link">Historique des tentatives</summary>
    <div className="mt-3 space-y-2 work-muted">
      <p>Tentative précédente · {attempt.status === 'failed' ? 'Échec' : attempt.status === 'cancelled' ? 'Arrêtée' : 'Terminée'}</p>
      {attempt.finishedAt && <p>{new Date(attempt.finishedAt).toLocaleString('fr-FR')}</p>}
      {attempt.error && <p className="break-words whitespace-pre-wrap">{attempt.error}</p>}
      <ol>{attempt.steps.map(step => <li key={step.id} className="py-1">
        {step.description} · {step.brain} · {step.status === 'done' ? 'Terminée' : step.status === 'failed' ? 'Échec' : 'Interrompue'}
        {step.durationMs != null && ` · ${Math.round(step.durationMs / 1000)} s`}
        {step.liveOutput && <pre className="work-console">{step.liveOutput}</pre>}
      </li>)}</ol>
    </div>
  </details>;
}
