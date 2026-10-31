import { useEffect, useState } from 'react';
import { Box, Download, Expand, Loader2, Ruler } from 'lucide-react';
import { cadArtifact, currentCadPreview } from '@/lib/cad';
import { useAppStore, type RunState } from '@/store/appStore';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from './ui/dialog';

const phases = { modeling: 'Modélisation de la pièce', checking: 'Mesures et vérifications',
  ready: 'Pièce vérifiée', failed: 'Modélisation à reprendre', cancelled: 'Travail arrêté' };

export function CadPanel({ run }: { run: RunState }) {
  const cad = run.cad;
  const theme = useAppStore(state => state.theme);
  const [image, setImage] = useState('');
  const [imageError, setImageError] = useState('');
  const [actionError, setActionError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [downloading, setDownloading] = useState('');
  const revision = cad?.snapshot?.document.revision;
  const imageHash = cad?.snapshot?.preview?.image.sha256;
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
  return <section className="work-widget" aria-label="Pièce CAO">
    <div className="flex items-center justify-between gap-3"><div className="work-eyebrow"><Box size={14} /> SolidCraft · CAO</div>
      {revision && <span className="work-muted text-[11px]">Révision {revision}</span>}</div>
    <h3 className="work-heading">{cad.title}</h3>
    <p className="flex gap-2 items-center mt-2 text-[12px] work-muted">{busy && <span className="work-pulse" />}{phases[status]}</p>
    <button className="relative w-full mt-4 overflow-hidden rounded-2xl border border-white/5 bg-gradient-to-b from-slate-900/60 to-transparent aspect-[8/5]"
      disabled={!image} onClick={() => setExpanded(true)} aria-label="Agrandir la pièce">
      {picture}{image && <span className="absolute right-3 bottom-3 flex items-center gap-1 text-[11px] rounded-full px-2 py-1 bg-black/60 text-white"><Expand size={12} /> Agrandir</span>}
      {captured?.preview && !current && <span className="absolute left-3 top-3 rounded-full px-2 py-1 text-[10px] bg-black/70 text-amber-200">Révision conservée · aperçu antérieur</span>}
    </button>
    {dimensions && captured && <dl className="grid grid-cols-2 gap-3 mt-4 text-[12px]">
      <div className="col-span-2"><dt className="work-muted flex gap-1 items-center"><Ruler size={12} /> Dimensions</dt><dd className="mt-1 font-medium">{dimensions.map(number).join(' × ')} mm</dd></div>
      <div><dt className="work-muted">Volume mesuré</dt><dd className="mt-1">{number(captured.geometry.volume_mm3)} mm³</dd></div>
      <div><dt className="work-muted">Géométrie</dt><dd className="mt-1">{captured.geometry.body_count} corps · {captured.geometry.closed_solid ? 'solide fermé' : 'surface ouverte'}</dd></div>
    </dl>}
    {!!captured?.checks.length && <details className="mt-4"><summary className="work-link">Contrôles mesurés · {captured.checks.length}</summary>
      <ul className="mt-3 space-y-2 text-[11px] work-muted">{captured.checks.map(check => <li key={check.criterion_id}>
        <span style={{ color: check.status === 'passed' ? 'var(--success)' : 'var(--warning)' }}>{check.status === 'passed' ? '✓' : '·'}</span> {check.diagnostic}
      </li>)}</ul></details>}
    {diagnostic && <p role="alert" className="mt-4 text-[12px] break-words" style={{ color: 'var(--warning)' }}>{diagnostic}</p>}
    {captured && <div className="flex flex-wrap gap-2 mt-5">
      <button className="work-primary" disabled={!!downloading} onClick={() => void download('native')}><Download size={13} /> Document éditable</button>
      {captured.document.exports.map((item) => <button key={item.path} className="work-secondary" disabled={!!downloading}
        onClick={() => void download(item.format)}>{item.format.toUpperCase()}</button>)}
    </div>}
    {actionError && <p role="alert" className="mt-3 text-[12px]" style={{ color: 'var(--warning)' }}>{actionError}</p>}
    <Dialog open={expanded} onOpenChange={setExpanded}><DialogContent data-theme={theme} className="sm:max-w-5xl rounded-3xl"
      style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border-subtle)' }}>
      <DialogTitle>{cad.title}</DialogTitle><DialogDescription style={{ color: 'var(--text-secondary)' }}>Révision {revision} · {current ? 'Aperçu de la pièce vérifiée' : 'Aperçu de la révision conservée'}</DialogDescription>
      <div className="h-[min(65vh,650px)]">{picture}</div>
    </DialogContent></Dialog>
  </section>;
}
