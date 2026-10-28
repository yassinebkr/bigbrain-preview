import { useEffect, useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ArrowLeft, ChevronDown, ExternalLink, Loader2, Maximize2, Minimize2, PanelRight, Layers, X } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { isBoardRun, nextProjectAttempt, reconcileWorkspace, runTitle, surfaceRegistry, webEntryPath, type WorkSurface } from '@/lib/morphable';
import { usePreview } from '@/lib/usePreview';
import { WorkOverview } from './WorkWidgets';
import { ResearchPanel } from './ResearchPanel';
import { isPartialResearch } from '@/lib/research';
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from './ui/dropdown-menu';

const labels = { preview: 'Aperçu', activity: 'Vue d’ensemble', files: 'Fichiers', verification: 'Tests', research: 'Recherche' };
const statuses = { running: 'En cours', done: 'Terminé', failed: 'Échec', cancelled: 'Annulé' };

const wideQuery = '(min-width: 1440px)';
const subscribeWidth = (notify: () => void) => {
  const media = window.matchMedia(wideQuery);
  media.addEventListener('change', notify);
  return () => media.removeEventListener('change', notify);
};

function PreviewSurface({ surface }: { surface: WorkSurface }) {
  const { url, error } = usePreview(webEntryPath(surface.run), true);
  return <div className="h-full flex flex-col min-h-0">
    <div className="flex justify-between items-center px-4 py-2 text-[11px] shrink-0" style={{ color: 'var(--text-tertiary)' }}>
      <span>Application locale</span>
      {url && <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-1" style={{ color: 'var(--accent-blue)' }}><ExternalLink size={12} /> Nouvel onglet</a>}
    </div>
    {url ? <iframe src={url} title={`Aperçu de ${runTitle(surface.run)}`} sandbox="allow-scripts allow-same-origin" className="flex-1 w-full min-h-0 border-0 bg-white" />
      : <p role={error ? 'alert' : 'status'} className="p-5 text-[12px]">{error || 'Ouverture de l’application…'}</p>}
  </div>;
}

export function SurfaceContent({ surface, select = () => {} }: { surface: WorkSurface; select?: (kind: WorkSurface['kind']) => void }) {
  const openFile = useAppStore((s) => s.openFileViewer);
  const setView = useAppStore((s) => s.setView);
  const { run, kind } = surface;
  const running = run.status === 'running' ? run.steps.filter((step) => step.status === 'running') : [];
  const done = run.steps.filter((step) => step.status === 'done');
  const agents = [...new Set(run.steps.map((step) => step.brain).filter(Boolean))];
  if (kind === 'preview') return <PreviewSurface surface={surface} />;
  if (kind === 'research') return <ResearchPanel run={run} />;
  if (kind === 'activity' && Object.keys(run.researches || {}).length > 0 && !run.projectPath && !run.files.length) return <ResearchPanel run={run} compact inspect={() => select('research')} />;
  const content = <div className={`${kind === 'activity' ? 'work-journal-content' : 'space-y-5 p-5'} text-[12px]`}>
    {run.error && <p role="alert" className="whitespace-pre-wrap break-words" style={{ color: 'var(--warning)' }}>{run.error}</p>}
    {kind === 'activity' && <>
      <p style={{ color: 'var(--text-secondary)' }}>{run.awaitingApproval ? 'En attente de ton accord dans le chat.' : `${done.length} étape${done.length > 1 ? 's' : ''} terminée${done.length > 1 ? 's' : ''} sur ${run.steps.length}`}</p>
      {!run.steps.length && <p style={{ color: 'var(--text-tertiary)' }}>{run.status === 'running' ? 'Préparation du plan…' : 'Aucune étape enregistrée.'}</p>}
      {running.map((step) => <div key={step.id} className="flex gap-2 items-start"><Loader2 size={14} className="animate-spin shrink-0 mt-0.5" /><div><p>{step.description}</p><p className="mt-1 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{step.brain}</p></div></div>)}
      {!!agents.length && <p className="text-[11px] break-words" style={{ color: 'var(--text-tertiary)' }}>Agents : {agents.join(' · ')}</p>}
      {!!run.steps.length && <>
        <ol className="work-journal-steps" aria-label="Étapes du run">{run.steps.map((step, index) => <li key={step.id}>
          <span className="work-stage-marker" aria-hidden="true">{index + 1}</span>
          <div className="min-w-0 flex-1"><p className="break-words">{step.description}</p><p className="mt-1 work-muted text-[11px]">{step.brain}{step.durationMs != null ? ` · ${(step.durationMs / 1000).toFixed(0)} s` : ''}</p>
          {step.liveOutput && <details className="mt-2"><summary className="work-link">Sortie de l’étape</summary><pre className="work-console mt-2" tabIndex={0}>{step.liveOutput}</pre></details>}</div>
          <span className="work-step-status" data-status={step.status === 'running' && run.status !== 'running' ? run.status : step.status}>{step.status === 'running' && run.status !== 'running' ? (run.status === 'failed' ? 'Échec' : 'Interrompu') : statuses[step.status]}</span>
        </li>)}</ol>
      </>}
    </>}
    {kind === 'files' && <>
      {run.projectPath && <p className="text-[11px] font-mono break-all" style={{ color: 'var(--text-tertiary)' }}>{run.projectPath}/</p>}
      <ul className="space-y-1">{run.files.map((file) => <li key={file.path}><button className="w-full text-left py-2 break-all hover:underline underline-offset-4" title={file.path} onClick={() => openFile(file.path)}>{run.projectPath && file.path.startsWith(`${run.projectPath}/`) ? file.path.slice(run.projectPath.length + 1) : file.path}</button></li>)}</ul>
    </>}
    {kind === 'verification' && run.verification && <>
      <p className="font-medium">{run.deliveryStatus === 'incomplete' ? 'Livraison non validée · contrôles enregistrés : ' : 'Verdict : '}{run.verification.verdict}</p>
      <ul className="space-y-3">{run.verification.stages.map((stage) => <li key={stage.name} className="flex justify-between gap-2"><span>{stage.name}</span><span style={{ color: stage.status === 'failed' ? 'var(--warning)' : 'var(--text-secondary)' }}>{stage.status}</span></li>)}</ul>
      <button className="underline underline-offset-4" onClick={() => setView('evidence')}>Consulter les preuves</button>
    </>}
    {isBoardRun(run) && <button className="underline underline-offset-4" onClick={() => setView('tasks')}>Ouvrir la taskboard</button>}
  </div>;
  return kind === 'activity' ? <WorkOverview run={run} select={select} journal={content} /> : content;
}

export function ContextWorkspace({ children }: { children: (ownsActivity: boolean) => ReactNode }) {
  const reducedMotion = useReducedMotion();
  const sessionId = useAppStore((s) => s.activeSessionKey);
  const runsById = useAppStore((s) => s.runsById);
  const completed = useAppStore((s) => s.completedRuns);
  const stopGeneration = useAppStore((s) => s.stopGeneration);
  const preference = useWorkspaceStore((s) => sessionId ? s.sessions[sessionId] : undefined);
  const update = useWorkspaceStore((s) => s.update);
  const inspect = useWorkspaceStore((s) => s.inspect);
  const wide = useSyncExternalStore(subscribeWidth, () => window.matchMedia(wideQuery).matches, () => false);
  const surfaces = surfaceRegistry(sessionId, [...Object.values(runsById), ...completed]);
  const state = reconcileWorkspace(surfaces, preference);
  const runs = surfaces.filter((surface) => surface.kind === 'activity');
  const expanded = state.mode === 'expanded';
  const explicit = state.mode === 'workspace' || expanded;
  const open = !!sessionId && (runs.length > 0 || !!preference?.selectedId) && state.mode !== 'focus';
  const visible = open && (explicit || wide);
  // Anchor the first real object once. Events can enrich it, not select a
  // concurrent run or open a preview server on the user's behalf.
  useEffect(() => {
    if (sessionId && !preference?.selectedId && runs[0]) {
      update(sessionId, { selectedId: runs[0].id });
    }
  }, [sessionId, preference?.selectedId, runs, update]);
  // Follow a newer attempt on this exact project, without letting unrelated
  // concurrent work (e.g. taskboard) steal the selected surface or reopen it.
  useEffect(() => {
    const selected = state.selected?.run;
    if (!sessionId || !selected) return;
    const next = nextProjectAttempt(selected, runs, preference?.selectedAt);
    if (next) update(sessionId, { selectedId: next.id });
  }, [sessionId, state.selected, runs, preference?.selectedAt, update]);
  const drag = useRef<{ x: number; width: number } | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const positions = useRef<Record<string, number>>({});
  useLayoutEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = positions.current[state.selected?.id || ''] || 0;
  }, [state.selected?.id, open]);
  const change = (value: Parameters<typeof update>[1]) => { if (sessionId) update(sessionId, value); };
  const close = () => change({ mode: 'focus' });
  const resize = (width: number) => change({ width: Math.min(1000, Math.max(400, width)) });
  return <section className="relative flex flex-col h-full min-h-0 min-w-0" aria-label="Workspace adaptatif" style={{ color: 'var(--text-primary)' }}>
    {(runs.length > 0 || !!preference?.selectedId) && <button
      className={`absolute right-4 top-2 z-10 rounded-lg px-3 py-2 text-[11px] ${open ? (explicit ? 'hidden' : 'min-[1440px]:hidden') : ''}`}
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
      onClick={() => change({ mode: 'workspace' })} aria-label="Ouvrir l’espace de travail">
      <PanelRight size={14} className="inline mr-2" />Travaux · {runs.length}
    </button>}
    <div className="context-layout flex-1 min-h-0 min-w-0" data-mode={visible ? expanded ? 'expanded' : 'open' : !open && preference?.mode !== 'focus' ? 'reserved' : 'closed'} style={{ '--context-width': `${state.width}px` } as CSSProperties}>
      <div className="context-chat min-w-0 h-full">{children(visible)}</div>
      {/* Reserve room for the first activity, but explicit closing returns
          that room to the chat. Later events respect the user's focus choice. */}
      <div className="context-rail relative min-w-0 min-h-0 flex">
      <AnimatePresence initial={false}>
      {open && <>
        <div role="separator" title="Glisser pour redimensionner" aria-label="Largeur de la surface" aria-orientation="vertical" aria-valuemin={400} aria-valuemax={1000} aria-valuenow={state.width} tabIndex={0}
          className={`${expanded ? 'hidden' : explicit ? 'hidden min-[1100px]:block' : 'hidden min-[1440px]:block'} absolute left-0 top-0 bottom-0 z-10 w-1 cursor-col-resize touch-none hover:bg-blue-500/20 focus-visible:bg-blue-500/30`}
          onKeyDown={(event) => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); resize(state.width + (event.key === 'ArrowLeft' ? 20 : -20)); } }}
          onPointerDown={(event) => { drag.current = { x: event.clientX, width: state.width }; event.currentTarget.setPointerCapture(event.pointerId); }}
          onPointerMove={(event) => { if (drag.current) resize(drag.current.width + drag.current.x - event.clientX); }}
          onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} />
        <motion.aside initial={{ opacity: 0, x: 22 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 22 }} transition={{ duration: reducedMotion ? 0 : .22 }} className={`context-island ${visible ? 'flex' : 'hidden'} flex-1 flex-col min-h-0 min-w-0`} data-expanded={expanded} aria-label="Surface contextuelle">
          <header className="p-4 flex items-start gap-3 shrink-0">
            <button className="min-[1100px]:hidden mt-1" aria-label="Retour au chat" onClick={close}><ArrowLeft size={16} /></button>
            <div className="context-identity" aria-hidden="true"><Layers size={19} /></div>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] uppercase tracking-[0.14em] work-muted mb-1">Atelier</p>
              {runs.length > 1 ? <DropdownMenu>
                <DropdownMenuTrigger asChild><button className="atelier-work-trigger" aria-label="Travail consulté"><span>{state.selected ? runTitle(state.selected.run) : 'Choisir un travail'}</span><ChevronDown size={14} /></button></DropdownMenuTrigger>
                <DropdownMenuContent align="start" sideOffset={10} className="atelier-work-menu">
                  <DropdownMenuLabel className="atelier-work-menu-label">Travaux de cette conversation</DropdownMenuLabel>
                  <DropdownMenuRadioGroup value={state.selected?.run.id || ''} onValueChange={(id) => { const surface = runs.find((s) => s.run.id === id); if (surface) inspect(surface.run); }}>
                    {runs.map(({ run }) => <DropdownMenuRadioItem key={run.id} value={run.id} className="atelier-work-option"><span className="min-w-0"><span className="atelier-work-option-title">{runTitle(run)}</span><span className="atelier-work-option-status" data-status={run.status}>{isPartialResearch(run) ? 'Incomplet' : statuses[run.status]}</span></span></DropdownMenuRadioItem>)}
                  </DropdownMenuRadioGroup>
                </DropdownMenuContent>
              </DropdownMenu> : <h2 className="text-[14px] font-medium line-clamp-2" title={state.selected?.run.description}>{state.selected ? (state.selected.run.projectName || state.selected.run.projectPath ? runTitle(state.selected.run) : Object.keys(state.selected.run.researches || {}).length ? 'Recherche documentaire' : 'Travail de la conversation') : 'Résultat indisponible'}</h2>}
              {state.selected && <p className="context-status text-[11px] mt-1 flex items-center gap-2" data-status={state.selected.run.status}>{state.selected.run.status === 'running' && !state.selected.run.awaitingApproval && <span className="work-pulse" aria-hidden="true" />}{state.selected.run.deliveryStatus === 'incomplete' ? 'Incomplet · non validé' : isPartialResearch(state.selected.run) ? 'Incomplet' : state.selected.run.awaitingApproval ? 'Ton accord est nécessaire' : statuses[state.selected.run.status]}</p>}
            </div>
            <button className="p-1" aria-label={expanded ? 'Redonner la place principale au chat' : 'Donner la place principale à cette activité'} onClick={() => change({ mode: expanded ? 'workspace' : 'expanded' })}>{expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
            <button className="p-1" aria-label="Fermer la surface" onClick={close}><X size={16} /></button>
          </header>
          <nav className="context-tabs flex shrink-0 overflow-x-auto" aria-label="Contenu de la surface">
            {surfaces.filter((s) => s.run.id === state.selected?.run.id).sort((a, b) => ['activity', 'research', 'preview', 'files', 'verification'].indexOf(a.kind) - ['activity', 'research', 'preview', 'files', 'verification'].indexOf(b.kind)).map((surface) => <button key={surface.id} aria-pressed={state.selected?.id === surface.id} className="text-[11px] shrink-0" onClick={() => change({ selectedId: surface.id })}>{labels[surface.kind]}</button>)}
          </nav>
          <div className="flex-1 overflow-y-auto min-h-0" ref={contentRef} onScroll={(event) => { if (state.selected) positions.current[state.selected.id] = event.currentTarget.scrollTop; }}>
            {visible && (state.selected ? <SurfaceContent key={state.selected.id} surface={state.selected} select={(kind) => { const surface = surfaces.find((item) => item.run.id === state.selected?.run.id && item.kind === kind); if (surface) change({ selectedId: surface.id }); }} /> : <p className="p-5 text-[12px]" role="status">Historique en cours de restauration ou résultat indisponible. Les autres travaux restent accessibles.</p>)}
          </div>
          <footer className="context-footer px-4 py-3 text-[11px] shrink-0 flex justify-between gap-2" style={{ color: 'var(--text-tertiary)' }}>
            <span>{state.selected?.run.awaitingApproval ? 'Ton accord est nécessaire' : state.selected?.run.status === 'running' ? 'Activité en direct' : 'Résultat conservé dans la conversation'}</span>
            {state.selected?.run.status === 'running' && <button className="shrink-0" onClick={stopGeneration}>Arrêter les travaux</button>}
          </footer>
        </motion.aside>
      </>}
      </AnimatePresence>
      </div>
    </div>
  </section>;
}
