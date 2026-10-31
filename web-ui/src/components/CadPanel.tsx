import { lazy, Suspense, useEffect, useState } from 'react';
import { Box, CheckCircle2, CircleHelp, Download, Expand, ExternalLink, Loader2, Ruler, XCircle } from 'lucide-react';
import { presentCadCheck } from '@/lib/cadChecks';
import { cadArtifact, cadDesktop, currentCadPreview } from '@/lib/cad';
import { useAppStore, type RunState } from '@/store/appStore';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from './ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu';

const phases = { modeling: 'Modélisation de la pièce', checking: 'Mesures et vérifications',
  ready: 'Pièce vérifiée', failed: 'Modélisation à reprendre', cancelled: 'Travail arrêté' };
const CadMeshViewer = lazy(() => import('./CadMeshViewer'));

export function CadPanel({ run }: { run: RunState }) {
  const cad = run.cad;
  const theme = useAppStore(state => state.theme);
  const [image, setImage] = useState('');
  const [imageError, setImageError] = useState('');
  const [actionError, setActionError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [downloading, setDownloading] = useState('');
  const [desktop, setDesktop] = useState<{ available?: boolean; diagnostic?: string }>({});
  const [launchMessage, setLaunchMessage] = useState('');
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
    <p className="flex gap-2 items-center mt-2 text-[12px] work-muted">{busy && <span className="work-pulse" />}{phases[status]}</p>
    <div className="relative w-full mt-4 overflow-hidden rounded-2xl border border-white/5 bg-gradient-to-b from-slate-900/60 to-transparent aspect-[8/5]">
      {!expanded && piece}{(image || hasMesh) && <button onClick={() => setExpanded(true)} aria-label="Agrandir la pièce"
        className="absolute right-3 top-3 flex items-center gap-1 text-[11px] rounded-full px-2 py-1 bg-black/60 text-white"><Expand size={12} /> Agrandir</button>}
      {captured?.preview && !current && <span className="absolute left-3 top-3 rounded-full px-2 py-1 text-[10px] bg-black/70 text-amber-200">Révision conservée · aperçu antérieur</span>}
    </div>
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
    {captured && <div className="flex flex-wrap gap-2 mt-5">
      <button className="work-secondary" disabled={!desktop.available || !!downloading} title={desktop.diagnostic || 'Ouvrir une copie éditable dans SolidCraft'}
        onClick={async () => {
          setActionError(''); setDownloading('gui');
          try { const result = await cadDesktop(cad, run.sessionId, 'open'); setLaunchMessage(result.message || 'Ouverture demandée.'); }
          catch (error) { setActionError(String(error)); }
          finally { setDownloading(''); }
        }}><ExternalLink size={13} /> Ouvrir dans SolidCraft</button>
      <DropdownMenu><DropdownMenuTrigger asChild>
        <button className="work-secondary !px-2.5" aria-label="Télécharger la pièce" title="Télécharger la pièce" disabled={!!downloading}>
          {downloading && downloading !== 'gui' ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
        </button>
      </DropdownMenuTrigger><DropdownMenuContent data-theme={theme} align="end" className="rounded-xl p-1.5"
        style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border-subtle)' }}>
        <DropdownMenuItem onSelect={() => void download('native')}>Document éditable · .sc</DropdownMenuItem>
        {captured.document.exports.map(item => <DropdownMenuItem key={item.path} onSelect={() => void download(item.format)}>
          {item.format.toUpperCase()}</DropdownMenuItem>)}
      </DropdownMenuContent></DropdownMenu>
    </div>}
    {launchMessage && <p role="status" className="mt-3 text-[11px] work-muted">{launchMessage}</p>}
    {actionError && <p role="alert" className="mt-3 text-[12px]" style={{ color: 'var(--warning)' }}>{actionError}</p>}
    <Dialog open={expanded} onOpenChange={setExpanded}><DialogContent data-theme={theme} className="sm:max-w-5xl rounded-3xl"
      style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border-subtle)' }}>
      <DialogTitle>{cad.title}</DialogTitle><DialogDescription style={{ color: 'var(--text-secondary)' }}>Révision {revision} · {current ? 'Aperçu de la pièce vérifiée' : 'Aperçu de la révision conservée'}</DialogDescription>
      <div className="h-[min(65vh,650px)]">{expanded && piece}</div>
    </DialogContent></Dialog>
  </section>;
}
