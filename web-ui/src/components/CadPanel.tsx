import { lazy, Suspense, useEffect, useState } from 'react';
import { Box, CheckCircle2, CircleHelp, Download, Expand, ExternalLink, Loader2, Ruler, XCircle } from 'lucide-react';
import { presentCadCheck } from '@/lib/cadChecks';
import { cadArtifact, cadDesktop, currentCadPreview, readPublishedCad } from '@/lib/cad';
import { useAppStore, type RunState } from '@/store/appStore';
import { editorWasOpen, selectEditor } from '@/lib/cadBrowser';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { surfaceId } from '@/lib/morphable';
import { retainedPreviewMode } from '@/lib/cadLiveRuntime';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu';

const phases = { modeling: 'Modélisation de la pièce', checking: 'Mesures et vérifications',
  ready: 'Pièce vérifiée', failed: 'Modélisation à reprendre', cancelled: 'Travail arrêté' };
const executionPhases = { deciding: 'Préparation de la prochaine étape', discovering: 'Consultation des outils',
  observing: 'Inspection de la géométrie', executing: 'Construction en cours', checkpoint: 'Étape conservée',
  repairing: 'Correction de l’étape', revising: 'Reprise de la construction' };
const CadMeshViewer = lazy(() => import('./CadMeshViewer'));
const CadBrowserEditor = lazy(() => import('./CadBrowserEditor'));
const CadLivePreview = lazy(() => import('./CadLivePreview'));

export function CadPanel({ run, expanded = false }: { run: RunState; expanded?: boolean }) {
  const recordedCad = run.cad;
  const reconcilePublication = useAppStore(state => state.reconcileCadPublication);
  const cad = recordedCad;
  useEffect(() => {
    if (!recordedCad || run.status === 'running' || (recordedCad.status === 'ready' && run.status === 'done' && run.deliveryStatus !== 'incomplete')) return;
    const controller = new AbortController();
    readPublishedCad(recordedCad, run.sessionId, controller.signal).then(value => {
      if (!controller.signal.aborted && value) reconcilePublication(run.id, run.sessionId, value);
    }).catch(() => {});
    return () => controller.abort();
  }, [recordedCad?.document_id, recordedCad?.sequence, run.id, run.sessionId, run.status, run.deliveryStatus, reconcilePublication]);
  const theme = useAppStore(state => state.theme);
  const [image, setImage] = useState('');
  const [imageError, setImageError] = useState('');
  const [actionError, setActionError] = useState('');
  const [editing, setEditing] = useState(false);
  const [previewMode, setPreviewMode] = useState<'solid' | 'construction'>(() => cad ? retainedPreviewMode(cad.document_id, run.sessionId) : 'solid');
  useEffect(() => { setEditing(cad ? editorWasOpen(cad.document_id, run.sessionId) : false); }, [cad?.document_id, run.sessionId]);
  useEffect(() => {
    if (run.status === 'running') setEditing(false);
  }, [run.status]);
  const [downloading, setDownloading] = useState('');
  const [desktop, setDesktop] = useState<{ available?: boolean; diagnostic?: string }>({});
  const [launchMessage, setLaunchMessage] = useState('');
  const [resuming, setResuming] = useState(false);
  const [recovery, setRecovery] = useState<{ label: string; enabled: boolean } | null>(null);
  useEffect(() => {
    setRecovery(null); setResuming(false);
    if (!cad) return;
    const controller = new AbortController();
    fetch('/api/cad/recovery', { method: 'POST', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' },
      body: JSON.stringify({ documentId: cad.document_id, sessionId: run.sessionId }) })
      .then(async response => {
        if (!response.ok) throw new Error('État de reprise indisponible');
        const value = await response.json();
        if (typeof value.label !== 'string' || typeof value.enabled !== 'boolean') throw new Error('État de reprise invalide');
        if (!controller.signal.aborted) setRecovery(value);
      }).catch(() => { if (!controller.signal.aborted) setRecovery({ label: 'Examiner le blocage', enabled: false }); });
    return () => controller.abort();
  }, [cad?.document_id, cad?.sequence, run.sessionId, run.status]);
  const revision = cad?.snapshot?.document.revision;
  const imageHash = cad?.snapshot?.preview?.image.sha256;
  useEffect(() => {
    setDesktop({}); setLaunchMessage('');
    if (!cad?.snapshot) return;
    const controller = new AbortController();
    cadDesktop(cad, run.sessionId, 'capability', controller.signal).then(setDesktop)
      .catch(error => { if (!controller.signal.aborted) setDesktop({ available: false, diagnostic: String(error) }); });
    return () => controller.abort();
  }, [cad?.document_id, run.sessionId, revision]);
  useEffect(() => {
    setImage(''); setImageError('');
    if (!cad?.snapshot?.preview) return;
    const controller = new AbortController();
    let url = '';
    cadArtifact(cad, run.sessionId, 'preview', controller.signal).then((blob) => {
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(blob); setImage(url);
    }).catch((error) => { if (!controller.signal.aborted) setImageError(String(error)); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [cad?.document_id, run.sessionId, revision, imageHash]);
  if (!cad) return null;
  const captured = cad.snapshot;
  const busy = run.status === 'running' && ['modeling', 'checking'].includes(cad.status);
  const interrupted = run.status !== 'running' && ['modeling', 'checking'].includes(cad.status);
  const status = interrupted ? run.status === 'cancelled' ? 'cancelled' : 'failed' : cad.status;
  const diagnostic = cad.diagnostic || (interrupted ? run.error || 'Cette opération a été interrompue avant sa validation.' : '');
  const current = currentCadPreview(cad) && run.status !== 'failed' && run.deliveryStatus !== 'incomplete';
  const dimensions = captured?.geometry.bounds_max_mm.map((maximum, index) => maximum - captured.geometry.bounds_min_mm[index]);
  const number = (value: number) => value.toLocaleString('fr-FR', { maximumFractionDigits: 3 });
  const download = async (kind: string) => {
    setActionError(''); setDownloading(kind);
    try {
      const blob = await cadArtifact(cad, run.sessionId, kind);
      const url = URL.createObjectURL(blob), anchor = document.createElement('a');
      anchor.href = url; anchor.download = `piece-r${revision}.${kind === 'native' ? 'sc' : kind}`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setActionError(String(error)); }
    finally { setDownloading(''); }
  };
  const picture = image ? <img src={image} alt={`Pièce ${cad.title}, révision ${revision}`} className="w-full h-full object-contain" />
    : <div className="flex flex-col items-center justify-center gap-3 h-full work-muted">{busy || captured?.preview && !imageError
      ? <Loader2 size={25} className="animate-spin motion-reduce:animate-none" /> : <Box size={34} strokeWidth={1.2} />}
      <p className="text-[12px] px-5 text-center">{imageError || captured?.preview_error || (captured ? 'Aperçu en préparation' : 'La pièce apparaîtra après la première capture.')}</p></div>;
  const hasMesh = captured?.document.exports.some(item => item.format === 'stl' && item.source_sha256 === captured.document.native.sha256);
  const piece = hasMesh ? <Suspense fallback={picture}><CadMeshViewer cad={cad} sessionId={run.sessionId} fallback={picture} /></Suspense> : picture;
  return <section className="work-widget" aria-label="Pièce CAO">
    <div className="flex items-center justify-between gap-3"><div className="work-eyebrow"><Box size={14} /> SolidCraft {captured?.document.engine_version} · CAO</div>
      {revision && <span className="work-muted text-[11px]">Révision {revision}</span>}</div>
    <h3 className="work-heading">{cad.title}</h3>
    {run.publishedRevision && <p className="work-muted mt-2 text-[11px]">Résultat actuellement validé · révision {run.publishedRevision}</p>}
    <p className="flex gap-2 items-center mt-2 text-[12px] work-muted">{busy && <span className="work-pulse" />}{phases[status]}</p>
    {cad.execution && <div className="mt-3 rounded-2xl border border-white/5 bg-white/[0.02] p-3.5" aria-label="Progression de la construction">
      <div className="flex items-center justify-between gap-3 text-[11px] work-muted">
        <span className="flex items-center gap-2">{busy && <Loader2 size={13} className="animate-spin motion-reduce:animate-none" />}
          {busy ? executionPhases[cad.execution.phase] : status === 'ready' ? 'Construction vérifiée' : 'Construction conservée'}</span>
        <span className="tabular-nums shrink-0">{cad.execution.accepted_steps} étape{cad.execution.accepted_steps > 1 ? 's' : ''}</span>
      </div>
      {cad.execution.current_step && <p className="mt-2 text-[12px] font-medium break-words">{cad.execution.current_step}</p>}
      <p className="mt-2 text-[10px] work-muted">{status === 'ready'
        ? 'La pièce et son historique ont passé les contrôles de cette révision.'
        : 'Les étapes conservées restent soumises aux vérifications de la pièce complète.'}</p>
    </div>}
    {(captured || cad.working) && <div className="relative z-[61] inline-flex gap-1 rounded-full p-1 mt-4" style={{background:'var(--bg-primary)'}} aria-label="Vue de la pièce">
      <button className="rounded-full px-3 py-1.5 text-[11px]" aria-pressed={!editing && previewMode === 'solid'} onClick={() => {selectEditor(cad.document_id, run.sessionId, false); setEditing(false); setPreviewMode('solid');}}>3D</button>
      {cad.working && <button className="rounded-full px-3 py-1.5 text-[11px]" aria-pressed={!editing && previewMode === 'construction'} onClick={() => {selectEditor(cad.document_id, run.sessionId, false); setEditing(false); setPreviewMode('construction');}}>Construction</button>}
      <button className="rounded-full px-3 py-1.5 text-[11px] disabled:opacity-40" aria-pressed={editing && expanded}
        title="Ouvrir SolidCraft Web dans l’Atelier"
        style={{background:editing && expanded ? 'var(--bg-surface)' : undefined}} onClick={() => {selectEditor(cad.document_id, run.sessionId, true); setEditing(true); useWorkspaceStore.getState().update(run.sessionId, {mode:'expanded', selectedId:surfaceId(run, 'cad')});}}>SolidCraft Web</button>
    </div>}
    {editing && expanded && captured && !busy && !cad.working && <Suspense fallback={<p role="status" className="work-muted mt-3 text-[12px]">Préparation de l’éditeur…</p>}>
      <CadBrowserEditor documentId={cad.document_id} sessionId={run.sessionId} revision={captured.document.revision} />
    </Suspense>}
    <div className={`${editing && expanded && captured && !busy && !cad.working ? 'hidden' : ''} relative w-full mt-4 overflow-hidden rounded-2xl border border-white/5 bg-gradient-to-b from-slate-900/60 to-transparent ${editing && expanded ? 'h-[65dvh]' : 'aspect-[8/5]'}`}>
      {cad.working ? <Suspense fallback={piece}><CadLivePreview cad={cad} sessionId={run.sessionId} mode={editing && expanded ? 'full' : previewMode} /></Suspense> : piece}{!expanded && (image || hasMesh || cad.working) && <button onClick={() => useWorkspaceStore.getState().update(run.sessionId, {mode:'expanded', selectedId:surfaceId(run, 'cad')})} aria-label="Agrandir la pièce"
        className="absolute right-3 top-3 flex items-center gap-1 text-[11px] rounded-full px-2 py-1 bg-black/60 text-white"><Expand size={12} /> Agrandir</button>}
    </div>
    {!(editing && expanded) && captured?.preview && !current && <p className="mt-2 text-[11px] text-amber-200">Révision conservée · aperçu antérieur</p>}
    {editing && expanded && <p className="work-muted text-[11px] mt-4">Mesures de la révision publiée {revision}</p>}
    {dimensions && captured && <dl className="grid grid-cols-2 gap-3 mt-4 text-[12px]">
      <div className="col-span-2"><dt className="work-muted flex gap-1 items-center"><Ruler size={12} /> Dimensions</dt><dd className="mt-1 font-medium">{dimensions.map(number).join(' × ')} mm</dd></div>
      <div><dt className="work-muted">Volume mesuré</dt><dd className="mt-1">{number(captured.geometry.volume_mm3)} mm³</dd></div>
      <div><dt className="work-muted">Géométrie</dt><dd className="mt-1">{captured.geometry.body_count} corps · {captured.geometry.closed_solid ? 'solide fermé' : 'surface ouverte'}</dd></div>
    </dl>}
    {!!captured?.checks.length && <details className="mt-5 rounded-2xl border border-white/5 bg-white/[0.02] p-3.5">
      <summary className="cursor-pointer text-[12px] font-medium select-none">Contrôles mesurés
        <span className="ml-2 work-muted font-normal">{captured.checks.filter(check => check.status === 'passed').length}/{captured.checks.length} conformes</span></summary>
      <ul className="mt-3 space-y-2.5">{captured.checks.map(check => {
        const detail = presentCadCheck(check);
        const passed = check.status === 'passed';
        const Icon = passed ? CheckCircle2 : check.status === 'failed' ? XCircle : CircleHelp;
        return <li key={check.criterion_id} className="rounded-xl bg-black/10 p-3 text-[12px]">
          <div className="flex items-start gap-2"><Icon size={15} className="shrink-0 mt-0.5" style={{ color: passed ? 'var(--success)' : 'var(--warning)' }} />
            <span className="font-medium flex-1 break-words">{detail.label}</span>
            <span className="text-[10px] shrink-0 rounded-full px-2 py-0.5" style={{ color: passed ? 'var(--success)' : 'var(--warning)', background: passed ? 'color-mix(in srgb, var(--success) 10%, transparent)' : 'color-mix(in srgb, var(--warning) 10%, transparent)' }}>
              {passed ? 'Conforme' : check.status === 'failed' ? 'À corriger' : 'À vérifier'}</span>
          </div>
          {detail.observed && <dl className="grid grid-cols-2 gap-3 mt-3 tabular-nums">
            <div><dt className="work-muted text-[10px]">Mesuré</dt><dd className="mt-1 font-medium">{detail.observed}</dd></div>
            <div><dt className="work-muted text-[10px]">Attendu</dt><dd className="mt-1">{detail.expected}</dd></div>
          </dl>}
          {detail.observed && <p className="work-muted text-[10px] mt-2">Tolérance : {detail.tolerance || 'voir le contrat de cette révision'}</p>}
          <details className="mt-2"><summary className="cursor-pointer work-muted text-[10px]">Détail technique</summary>
            <p className="mt-2 work-muted text-[10px] break-words">{check.diagnostic}</p></details>
        </li>;
      })}</ul></details>}
    {diagnostic && <p role="alert" className="mt-4 text-[12px] break-words" style={{ color: 'var(--warning)' }}>{diagnostic}</p>}
    {['failed', 'cancelled'].includes(status) && <button className="work-secondary mt-4" disabled={resuming || !recovery?.enabled}
      onClick={async () => {
        setResuming(true); setActionError('');
        try {
          const response = await fetch('/api/cad/resume', { method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' },
            body: JSON.stringify({ documentId: cad.document_id, sessionId: run.sessionId }) });
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || 'Reprise indisponible');
          setLaunchMessage('Reprise demandée depuis le travail conservé.');
        } catch (error) { setActionError(String(error)); setResuming(false); }
      }}>{resuming ? 'Reprise demandée…' : recovery?.label || 'Vérification de la reprise…'}</button>}
    {captured && <div className="flex flex-wrap gap-2 mt-5">
      <DropdownMenu><DropdownMenuTrigger asChild>
        <button className="work-secondary !px-2.5" aria-label="Télécharger la pièce" title="Télécharger la pièce" disabled={!!downloading}>
          {downloading && downloading !== 'gui' ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
        </button>
      </DropdownMenuTrigger><DropdownMenuContent data-theme={theme} align="end" className="z-[80] rounded-xl p-1.5"
        style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border-subtle)' }}>
        <DropdownMenuItem onSelect={() => void download('native')}>Document éditable · .sc</DropdownMenuItem>
        {captured.document.exports.map(item => <DropdownMenuItem key={item.path} onSelect={() => void download(item.format)}>
          {item.format.toUpperCase()}</DropdownMenuItem>)}
        <DropdownMenuItem disabled={!desktop.available || !!downloading} onSelect={() => {
          setActionError(''); setDownloading('gui');
          void cadDesktop(cad, run.sessionId, 'open').then(result => setLaunchMessage(result.message || 'Ouverture demandée.'))
            .catch(error => setActionError(String(error))).finally(() => setDownloading(''));
        }}><ExternalLink size={13} /> Ouvrir une copie dans l’application de bureau</DropdownMenuItem>
      </DropdownMenuContent></DropdownMenu>
    </div>}
    {launchMessage && <p role="status" className="mt-3 text-[11px] work-muted">{launchMessage}</p>}
    {actionError && <p role="alert" className="mt-3 text-[12px]" style={{ color: 'var(--warning)' }}>{actionError}</p>}
  </section>;
}
