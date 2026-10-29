import { useEffect, useRef, useState } from 'react';
import { Check, ChevronRight, FileCode2, FolderOpen, Loader2, Play, ShieldCheck, Terminal, X } from 'lucide-react';
import { useAppStore, type RunState } from '@/store/appStore';
import { projectRunKey, pythonEntry, useProjectRunStore } from '@/store/projectRunStore';
import { isBoardRun, webEntryPath, type SurfaceKind } from '@/lib/morphable';
import { ContractCriteria, StackSummary, SourceConsent } from './ContractCard';
import { composeWidgets, parseWidgetProposal } from '@/lib/widgetPolicy';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { ResearchActivity } from './ResearchPanel';

const stageLabels: Record<string, string> = { syntax: 'Syntaxe', compile: 'Compilation', run: 'Exécution', contracts: 'Fichiers attendus', tests: 'Tests', entry_point: 'Point d’entrée', semantics: 'Revue indépendante', attached_delivery: 'Livraison du dossier local' };

export function VerificationWidget({ run }: { run: RunState }) {
  const setView = useAppStore((s) => s.setView);
  if (!run.verification) return null;
  const verification = run.verification;
  const passed = verification.stages.filter((stage) => stage.status === 'passed').length;
  const failed = verification.stages.filter((stage) => stage.status === 'failed').length;
  return <section className="work-widget" aria-label="Vérifications du livrable">
    <div className="work-eyebrow"><ShieldCheck size={14} /> Vérifications</div>
    <h3 className="work-heading">{run.deliveryStatus === 'incomplete' ? 'Livraison non validée' : verification.verdict === 'passed' ? 'Vérifications réussies' : verification.verdict === 'failed' ? 'Des points restent à corriger' : 'Vérifications non concluantes'}</h3>
    <p className="text-[12px] mt-3 work-muted">{passed} contrôle{passed > 1 ? 's' : ''} réussi{passed > 1 ? 's' : ''}{failed ? ` · ${failed} en échec` : ''}{verification.attempt ? ` · tentative ${verification.attempt}` : ''}</p>
    <div className="work-checks" aria-hidden="true">{verification.stages.map((stage) => <span key={stage.name} data-status={stage.status} />)}</div>
    <details className="mt-4"><summary className="work-link">Détails des vérifications</summary><div className="mt-3 space-y-2.5">{verification.stages.map((stage) => <div key={stage.name} className="flex items-center gap-2 text-[12px]">
      {stage.status === 'passed' ? <Check size={13} style={{ color: 'var(--success)' }} /> : <span className="w-[13px] text-center" style={{ color: 'var(--warning)' }}>{stage.status === 'failed' ? '×' : '·'}</span>}
      <span className="flex-1">{stageLabels[stage.name] || stage.name}</span><span style={{ color: 'var(--text-tertiary)' }}>{stage.status === 'passed' ? 'Réussi' : stage.status === 'failed' ? 'Échec' : stage.status}</span>
    </div>)}</div></details>
    <button className="work-link mt-4" onClick={() => setView('evidence')}>Consulter les preuves <ChevronRight size={12} /></button>
  </section>;
}

function ProposalWidget({ run }: { run: RunState }) {
  const proposal = useAppStore((s) => s.sessionProposals[run.sessionId]);
  const activeProposal = useAppStore((s) => s.contractProposal);
  const sending = useAppStore((s) => s.contractSending);
  const error = useAppStore((s) => s.contractError);
  const decide = useAppStore((s) => s.sendContractDecision);
  if (!proposal || proposal.planId !== run.id) return <p className="work-muted">Le contrat de ce travail est en cours de restauration.</p>;
  const stack = proposal.contracts.find((item) => item.startsWith('[Stack]'));
  const canDecide = activeProposal?.planId === proposal.planId && activeProposal?.designId === proposal.designId;
  return <section className="work-widget" aria-label="Proposition à approuver">
    <div className="work-eyebrow">{proposal.target?.mode === 'existing' ? 'Modification du projet' : 'Avant de construire'}</div>
    <h3 className="work-heading">{proposal.target?.mode === 'existing' ? 'Valider les changements proposés' : 'Voici ce qui sera livré'}</h3>
    {proposal.target && <code className="block text-[11px] break-all mt-3 work-muted">{proposal.target.path}</code>}
    {stack && <StackSummary value={stack} />}
    <ContractCriteria contracts={proposal.contracts} />
    <SourceConsent value={proposal.sourceTransmission} />
    <div className="mt-5 flex flex-wrap gap-2"><button disabled={sending || !canDecide} className="work-primary" onClick={() => void decide(true)}>{sending ? <Loader2 size={14} className="animate-spin motion-reduce:animate-none" /> : <Check size={14} />} Approuver et lancer</button>
      <button disabled={sending || !canDecide} className="work-secondary" onClick={() => void decide(false)}><X size={13} /> Refuser</button></div>
    {canDecide && error && <p role="alert" className="text-[12px] mt-3" style={{ color: 'var(--warning)' }}>{error}</p>}
  </section>;
}

export function PythonConsole({ run }: { run: RunState }) {
  const launch = useProjectRunStore((s) => s.launches[projectRunKey(run)]);
  const execute = useProjectRunStore((s) => s.launch);
  const live = useAppStore((s) => launch?.runId ? s.liveRuns[launch.runId] : undefined);
  const outputRef = useRef<HTMLPreElement>(null);
  const [follow, setFollow] = useState(true);
  const busy = !!launch?.pending || (!!live && !live.done) || (!!launch?.awaitingEvents && !live);
  const stdout = live?.out || live?.result?.stdout || '';
  const stderr = live?.err || live?.result?.stderr || '';
  const output = `${stdout}${stderr ? `\n${stderr}` : ''}`;
  useEffect(() => { if (follow && outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight; }, [output, follow]);
  return <section className="work-widget" aria-label="Console Python">
    <div className="work-eyebrow"><Terminal size={14} /> Exécution Python</div>
    <code className="block text-[11px] mt-2 break-all work-muted">{pythonEntry(run)}</code>
    <button className="work-primary mt-4" disabled={busy || !pythonEntry(run)} onClick={() => void execute(run)}>{busy ? <Loader2 size={14} className="animate-spin motion-reduce:animate-none" /> : <Play size={14} />}{busy ? 'Exécution en cours' : launch ? 'Lancer une nouvelle exécution' : 'Lancer le projet'}</button>
    {launch && <div className="mt-4">
      <div className="flex justify-between text-[11px] mb-2 work-muted"><span>{live?.done ? `Terminé · code ${live.result?.exitCode ?? '?'}` : busy ? 'Sortie en direct' : 'Résultat non disponible'}</span><button aria-pressed={follow} onClick={() => setFollow(!follow)}>{follow ? 'Suivi activé' : 'Reprendre le suivi'}</button></div>
      <pre ref={outputRef} aria-label="Sortie Python" tabIndex={0} className="work-console" onScroll={(event) => { const el = event.currentTarget; if (el.scrollHeight - el.scrollTop - el.clientHeight > 40) setFollow(false); }}>{output || (busy ? 'En attente de sortie…' : launch.error || 'Le suivi de cette exécution n’est pas disponible après rechargement. Aucun code n’a été relancé automatiquement.')}</pre>
      {live?.done && (live.result?.error || live.result?.timedOut || live.result?.exitCode !== 0) && <p role="alert" className="text-[12px] mt-2" style={{ color: 'var(--warning)' }}>{live.result.error || (live.result?.timedOut ? 'Délai d’exécution dépassé' : 'Cette exécution a échoué. Consulte la sortie ci-dessus.')}</p>}
    </div>}
  </section>;
}

export function WorkOverview({ run, select, journal }: { run: RunState; select: (kind: SurfaceKind) => void; journal: React.ReactNode }) {
  const setView = useAppStore((s) => s.setView);
  const setFile = useAppStore((s) => s.setPendingOpenFile);
  const setProject = useAppStore((s) => s.setCurrentProject);
  const openFile = useAppStore((s) => s.openFileViewer);
  const [openError, setOpenError] = useState('');
  const board = isBoardRun(run);
  const entry = pythonEntry(run);
  const preview = webEntryPath(run);
  const running = run.status === 'running';
  const current = running ? run.steps.filter((step) => step.status === 'running') : [];
  const latestOutput = [...run.steps].reverse().find((step) => step.liveOutput)?.liveOutput;
  const launch = useProjectRunStore((s) => s.launches[projectRunKey(run)]);
  const execute = useProjectRunStore((s) => s.launch);
  const choice = useWorkspaceStore((s) => s.sessions[run.sessionId]?.widgetChoices?.[run.id]);
  const acceptWidgets = useWorkspaceStore((s) => s.acceptWidgets);
  const resetWidgets = useWorkspaceStore((s) => s.resetWidgets);
  const widgets = composeWidgets(run, choice?.widgets, !!launch);
  const proposal = parseWidgetProposal(run.widgetProposal);
  const widgetLabels = { files: 'Fichiers', verification: 'Vérifications', console: 'Console Python', preview: 'Accès à l’aperçu' };
  const openProject = async () => {
    if (run.localProject) {
      try {
        if (useAppStore.getState().activeSessionKey !== run.sessionId) throw new Error('Ouvre la conversation de ce travail avant son dossier.');
        const response = await fetch('/api/local-projects/select', { method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-BigBrain-Local': '1' },
          body: JSON.stringify({ sessionId: run.sessionId, projectId: run.localProject.project_id }) });
        if (!response.ok) throw new Error('Le dossier local est indisponible. Vérifie ses droits dans le workspace.');
        sessionStorage.setItem(`bigbrain-workspace-origin:${run.sessionId}`, 'local');
        setView('workspace');
      } catch (error) { setOpenError(String(error)); }
      return;
    }
    if (!entry) return;
    setOpenError('');
    try {
      if (run.projectPath) {
        const response = await fetch('/api/fs/current-project', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project: run.projectPath }) });
        if (!response.ok) throw new Error('Impossible d’ouvrir ce projet dans le workspace.');
        setProject(run.projectPath);
      }
      setFile(entry); setView('workspace');
    } catch (error) { setOpenError(String(error)); }
  };
  return <div className="work-overview">
    {run.awaitingApproval ? <ProposalWidget run={run} /> : <section className="work-widget" aria-label="Objet du travail">
      <div className="work-eyebrow">{running && <span className="work-pulse" aria-hidden="true" />}{board ? 'Organisation' : running ? 'En construction' : 'Livrable'}</div>
      <h3 className="work-heading">{run.deliveryStatus === 'incomplete' ? 'Projet incomplet · non validé' : running ? 'Le travail prend forme' : run.status === 'done' ? 'Le résultat est disponible' : run.status === 'failed' ? 'Le travail a rencontré un obstacle' : 'Travail arrêté'}</h3>
      {run.error && <p role="alert" className="mt-3 text-[12px] leading-relaxed break-words" style={{ color: 'var(--warning)' }}>{run.error}</p>}
      {running && <div className="mt-5 space-y-4">{current.length ? current.map((step) => <div key={`${step.id}:${step.description}`} className="work-live-step flex gap-3"><span className="work-pulse mt-1" /><div className="min-w-0"><p className="text-[13px] leading-relaxed break-words">{step.description}</p><p className="work-muted text-[11px] mt-1">{step.brain}{step.durationMs != null ? ` · ${(step.durationMs / 1000).toFixed(0)} s écoulées` : ''}</p></div></div>) : <p className="work-muted text-[12px]">{run.steps.length ? 'Préparation de la prochaine étape…' : 'Préparation du plan…'}</p>}</div>}
      {running && !!run.steps.length && <p className="work-muted text-[11px] mt-4" aria-label="Avancement observé">{run.steps.filter((step) => step.status === 'done').length} étapes terminées · {current.length} actives{run.files.length ? ` · ${run.files.length} fichiers enregistrés` : ''}</p>}
      {!!run.steps.length && running && <div className="work-stage-list" aria-label="Étapes récentes">{run.steps.slice(-3).map((step, index) => <div className="work-stage" data-status={step.status} key={step.id}><span className="work-stage-marker">{step.status === 'done' ? <Check size={12} /> : step.status === 'failed' ? <X size={12} /> : run.steps.length - Math.min(3, run.steps.length) + index + 1}</span><span className="line-clamp-2" title={step.description}>{step.description}</span></div>)}</div>}
      {run.projectPath && <code className="block text-[11px] break-all mt-3 work-muted">{run.projectPath}/</code>}
      {!board && run.entryPoint && <div className="work-artifact mt-5" aria-label="Point d’entrée du livrable"><div className="work-artifact-icon"><FileCode2 size={25} strokeWidth={1.4} /></div><div className="min-w-0"><p className="text-[13px] font-medium break-all">{run.entryPoint}</p><p className="text-[11px] mt-1 work-muted">{run.deliverableType === 'python' ? 'Programme Python' : run.deliverableType === 'web_app' ? 'Application web' : 'Point d’entrée déclaré'}</p></div></div>}
      <div className="flex flex-wrap gap-2 mt-5">
        {run.localProject && <button className="work-primary" onClick={() => void openProject()}><FolderOpen size={14} /> Ouvrir le dossier local</button>}
        {board && <button className="work-primary" onClick={() => setView('tasks')}>Ouvrir la taskboard</button>}
        {preview && <button className="work-primary" onClick={() => select('preview')}><Play size={14} /> Ouvrir l’aperçu</button>}
        {entry && <button className="work-secondary" onClick={() => void openProject()}><FolderOpen size={14} /> Ouvrir le projet</button>}
        {entry && !widgets.includes('console') && <button className="work-primary" onClick={() => void execute(run)}><Play size={14} /> Lancer le projet</button>}
        {!board && !!run.files.length && <button className="work-link" onClick={() => select('files')}><FileCode2 size={14} /> {run.files.length} fichier{run.files.length > 1 ? 's' : ''} disponible{run.files.length > 1 ? 's' : ''}</button>}
      </div>
      {openError && <p role="alert" className="text-[12px] mt-3" style={{ color: 'var(--warning)' }}>{openError}</p>}
    </section>}
    {Object.entries(run.researches || {}).map(([id, research]) => <ResearchActivity key={id} research={research} live={running} inspect={() => select('research')} />)}
    {widgets.map((kind) => kind === 'console' ? <PythonConsole key={kind} run={run} />
      : kind === 'verification' ? <VerificationWidget key={kind} run={run} />
      : kind === 'preview' ? <section key={kind} className="work-widget" aria-label="Widget aperçu"><div className="work-eyebrow">Application disponible</div><p className="text-[12px] mt-3 work-muted">L’aperçu ne démarre que si tu l’ouvres.</p><button className="work-secondary mt-3" onClick={() => select('preview')}>Afficher l’application</button></section>
      : <section key={kind} className="work-widget" aria-label="Widget fichiers"><div className="work-eyebrow"><FileCode2 size={14} /> Fichiers du livrable · {run.files.length}</div><div className="mt-3">{run.files.slice(0, 3).map((file) => <button key={file.path} className="work-file-row" title={file.path} onClick={() => openFile(file.path)}><FileCode2 size={14} className="shrink-0" /><span className="truncate">{file.path.split('/').pop()}</span><ChevronRight size={12} className="ml-auto shrink-0" /></button>)}</div><button className="work-link mt-3" onClick={() => select('files')}>Consulter les fichiers <ChevronRight size={12} /></button></section>)}
    {!widgets.length && latestOutput && <details className="work-widget"><summary className="work-link">Dernière sortie enregistrée</summary><pre className="work-console mt-3">{latestOutput}</pre></details>}
    {proposal && <details className="work-journal" aria-label="Composition proposée"><summary className="work-link">Suggestion de composition{choice ? ' · choix enregistré' : ''}</summary><p className="text-[12px] mt-3 work-muted">L’architecte propose : {proposal.widgets.map((kind) => widgetLabels[kind]).join(' · ')}. Seuls les widgets disponibles seront affichés. Aucune exécution ne sera déclenchée.</p><div className="flex flex-wrap gap-2 mt-3"><button className="work-secondary" onClick={() => acceptWidgets(run)}>Utiliser cette composition</button>{choice && <button className="work-link" onClick={() => resetWidgets(run)}>Revenir à la composition standard</button>}</div></details>}
    <details className="work-journal"><summary className="work-link">Activité et journal technique</summary>{journal}</details>
  </div>;
}
