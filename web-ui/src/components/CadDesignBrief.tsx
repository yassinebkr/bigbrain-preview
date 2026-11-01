import type { CadBrief } from '@/lib/cadBrief';
import { AttachmentPreview } from './AttachmentPreview';

export function CadDesignBrief({ brief }: { brief: CadBrief }) {
  return <section className="work-widget" aria-label="Définition de la pièce">
    <div className="work-eyebrow">Conception · version {brief.revision}</div>
    <h3 className="work-heading">{brief.drawing?.title || 'Précisons la pièce'}</h3>
    {!!brief.sources.length && <div className="mt-4 flex flex-wrap gap-2" aria-label="Sources de la conception">
      {brief.sources.map(source => <AttachmentPreview key={source.id} attachment={source} />)}
    </div>}
    {brief.question && <div className="mt-4 rounded-xl p-3 bg-sky-400/10 border border-sky-400/15">
      <p className="text-[10px] uppercase tracking-wider work-muted mb-2">À préciser</p>
      <p className="text-sm leading-relaxed">{brief.question}</p>
    </div>}
    {!!brief.drawing?.dimensions.length && <dl className="mt-4 space-y-3">
      {brief.drawing.dimensions.map(dimension => <div key={dimension.id} className="flex justify-between gap-4 text-xs">
        <dt className="work-muted">{dimension.label}</dt>
        <dd className="text-right shrink-0">{dimension.value === null ? 'À préciser' : `${dimension.value} ${dimension.unit}`}
          <span className="block text-[10px] work-muted">{({ explicit: 'Lue sur le dessin', derived: 'Déduite', user: 'Précisée par toi', unresolved: 'Inconnue' } as Record<string, string>)[dimension.origin]}</span>
        </dd>
      </div>)}
    </dl>}
    {!!brief.exchanges.length && <details className="mt-4 text-xs"><summary className="work-link">Précisions conservées · {brief.exchanges.length}</summary>
      <ol className="mt-3 space-y-3">{brief.exchanges.map((exchange, index) => <li key={exchange.message_id || index} className="rounded-xl p-3 bg-white/[0.03]">
        <p className="leading-relaxed whitespace-pre-wrap">{exchange.user}</p>
        <p className="work-muted mt-2 leading-relaxed">{exchange.assistant}</p>
      </li>)}</ol>
    </details>}
  </section>;
}
