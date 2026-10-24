import { useEffect, useRef, useState } from 'react';
import { ExternalLink, Loader2, Search } from 'lucide-react';
import type { RunState } from '@/store/appStore';
import { publicLink, type ResearchView } from '@/lib/research';

const tools: Record<string, string> = { plan: 'Préparer les questions', search: 'Chercher des sources',
  open: 'Lire une source', assess: 'Comparer les preuves', conclude: 'Conclure sur les preuves', clarify: 'Préciser la demande' };
const verdicts = { supported: 'Étayé', contested: 'Contesté', unverified: 'Non vérifié', refuted: 'Réfuté' };
const statuses = { running: 'Recherche en cours', completed: 'Recherche terminée', partial: 'Recherche incomplète',
  unavailable: 'Recherche indisponible', clarification: 'Précision nécessaire', cancelled: 'Recherche arrêtée' };
const kinds: Record<string, string> = { primary: 'Source primaire', secondary: 'Source secondaire', testimony: 'Témoignage', unknown: 'Nature non établie', unassessed: 'Non évaluée' };
const phases: Record<string, string> = { http_loading: 'Chargement de la page HTTP', cache_hit: 'Lecture de l’observation en cache',
  http_cache_for_browser: 'Réutilisation de la page HTTP pour le navigateur', extracting: 'Extraction des passages',
  selecting_context: 'Sélection des sections selon la question', browser_loading: 'Lecture dans le navigateur',
  browser_request: 'Chargement des ressources de la page', browser_closed: 'Navigateur fermé · traitement du résultat' };
const access: Record<string, string> = { needs_context: 'Sélection insuffisante · lecture à préciser', requires_browser: 'Contenu JavaScript · navigateur nécessaire',
  blocked: 'Accès bloqué', authentication_required: 'Authentification nécessaire', rate_limited: 'Accès limité par le site',
  browser_unavailable: 'Navigateur indisponible', snapshot_changed: 'Observation différente · sections à sélectionner à nouveau',
  focus_missing: 'Terme absent de l’observation', context_invalid: 'Section demandée invalide', timeout: 'Délai de lecture dépassé' };

export function researchActivity(research: ResearchView) {
  const activity = research.activity;
  if (activity?.stage === 'research_acquisition' && activity.phase) return phases[activity.phase] || 'Lecture de la source';
  if (activity?.stage === 'research_assessing') return 'Revue indépendante des observations originales';
  if (activity?.stage === 'research_review_evidence') return 'Passages complémentaires consultés par la revue';
  if (activity?.stage === 'research_deciding') return 'Choix de la prochaine action';
  if (research.current_action?.tool === 'open' && (research.current_action.focus || research.current_action.group_ids?.length)) return 'Lecture ciblée des sections';
  return research.current_action ? tools[research.current_action.tool] || 'Analyse en cours' : 'Choix de la prochaine action';
}

// This compact widget also appears in the default overview; detailed evidence
// stays in the research surface instead of duplicating a second full journal.
export function ResearchActivity({ research, live, inspect }: { research: ResearchView; live: boolean; inspect?: () => void }) {
  const running = live && research.status === 'running';
  const source = research.sources.find((s) => s.id === (research.activity?.source_id || research.current_action?.source_id));
  return <section className="work-widget" aria-label="Activité de recherche">
    <div className="work-eyebrow"><Search size={14} /> Recherche documentaire</div>
    <p className="mt-3 text-[12px] flex gap-2 items-center" role="status">
      {running && <Loader2 size={14} className="animate-spin motion-reduce:animate-none" />}
      {running ? researchActivity(research) : research.status === 'running' ? 'Recherche interrompue · état conservé' : statuses[research.status]}
    </p>
    <details className="mt-2 text-[12px]"><summary className="work-link">Demande initiale</summary><p className="mt-2 break-words">{research.objective}</p></details>
    {running && source && <p className="work-muted mt-2 text-[11px] break-words">{source.acquisition?.title || source.title || source.url}</p>}
    {running && research.activity?.request_index != null && <p className="work-muted mt-2 text-[11px]">Ressource navigateur {research.activity.request_index}</p>}
    {inspect && <button className="work-link mt-3" onClick={inspect}>Suivre la recherche et ses preuves</button>}
  </section>;
}

function SourcePassages({ passages }: { passages: ResearchView['passages'] }) {
  const [visible, setVisible] = useState(20);
  return <>
    {passages.slice(0, visible).map((p) => <div key={p.id} className="mt-3 work-muted">
      <p className="text-[10px]">{p.review_only ? 'Observation complémentaire de la revue' : 'Passage sélectionné'} · {p.id}{p.clipped ? ' · extrait coupé' : ''}</p>
      {!!p.context?.length && <p className="text-[11px] mt-1">{p.context.join(' › ')}</p>}
      <p className="mt-1 whitespace-pre-wrap break-words">{p.text}</p>
    </div>)}
    {visible < passages.length && <button className="work-link mt-3" onClick={() => setVisible(visible + 20)}>Afficher d’autres passages ({passages.length - visible} restants)</button>}
  </>;
}

function ResearchWork({ research, live, compact, inspect }: { research: ResearchView; live: boolean; compact: boolean; inspect?: () => void }) {
  const [follow, setFollow] = useState(true);
  const log = useRef<HTMLDivElement>(null);
  const running = live && research.status === 'running';
  const read = research.sources.filter((source) => source.status === 'read');
  const assessed = research.assessments[0]?.source_assessments || [];
  useEffect(() => { if (follow && log.current) log.current.scrollTop = log.current.scrollHeight; }, [research.revision, follow]);
  return <section className="work-overview" aria-label="Suivi de recherche">
    <div className="work-widget">
      <div className="work-eyebrow"><Search size={14} /> Recherche documentaire</div>
      <h3 className="work-heading flex gap-2 items-start" role="status">
        {running && <Loader2 size={14} className="animate-spin motion-reduce:animate-none" />}
        {research.status === 'running' && !live ? 'Recherche interrompue · état conservé' : statuses[research.status]}
      </h3>
      <details className="mt-3 text-[12px]"><summary className="work-link">Demande initiale</summary><p className="mt-2 break-words leading-relaxed">{research.objective}</p></details>
      {running && <p className="text-[12px] mt-3" aria-live="polite">{researchActivity(research)}
        {research.current_action?.query && <span className="block mt-2 work-muted break-words">{research.current_action.query}</span>}</p>}
      {running && research.activity?.source_id && <p className="mt-2 text-[11px] work-muted break-words">Source : {research.sources.find((s) => s.id === research.activity?.source_id)?.url || research.activity.source_id}
        {research.activity.request_index != null ? ` · ressource navigateur ${research.activity.request_index}` : ''}</p>}
      <div className="flex flex-wrap gap-2 mt-4 text-[11px] work-muted" aria-label="Bilan de recherche"><span>{read.length} source{read.length > 1 ? 's' : ''} lue{read.length > 1 ? 's' : ''}</span><span>· {research.claims.length} conclusion{research.claims.length > 1 ? 's' : ''}</span><span>· {Math.round(research.elapsed_seconds)} s observées</span></div>
      {(research.status === 'partial' || research.status === 'unavailable' || research.assessment_error) && <div role="alert" className="rounded-xl p-3 mt-4 text-[12px] leading-relaxed" style={{ background: 'var(--bg-primary)', color: 'var(--warning)' }}>
        <p>{research.diagnostic ? 'Le modèle a renvoyé un format de réponse invalide.' : !read.length ? 'La recherche s’est arrêtée avant de lire une source.' : 'La recherche n’a pas pu établir toutes les conclusions.'}</p>
        <p className="mt-1 work-muted">{read.length ? 'Les passages déjà consultés restent disponibles.' : 'Aucune conclusion n’a été vérifiée.'}</p>
      </div>}
      <details className="mt-4 text-[11px] work-muted"><summary className="work-link">Usage et diagnostic</summary>
      <p className="mt-3">{research.counts.searches}/{research.limits.searches} recherches · {research.counts.pages}/{research.limits.pages} lectures tentées · {Math.round(research.elapsed_seconds)}/{research.limits.seconds} s observées · {research.counts.reviews ?? 0}/{research.limits.reviews ?? 2} revues</p>
      {research.limits.browsers != null && <p className="mt-2 text-[11px] work-muted">{research.counts.browsers ?? 0}/{research.limits.browsers} lectures navigateur tentées</p>}
      <p className="mt-2 text-[11px] work-muted">{research.usage.reported_tokens ?? 0} tokens rapportés
        {research.usage.unknown_usage_calls ? ` · usage inconnu pour ${research.usage.unknown_usage_calls} appel(s)` : ''}
        {` · coût ${research.usage.cost_usd == null ? 'inconnu' : `${research.usage.cost_usd.toFixed(4)} $`}`}</p>
      {!!research.usage.allowance_used && <p className="mt-1 text-[11px] work-muted">Enveloppe consommée : {research.usage.allowance_used}/{research.limits.tokens} · inclut une réserve estimée si l’usage manque</p>}
      {research.reason && research.status !== 'running' && <pre className="mt-3 text-[11px] whitespace-pre-wrap break-words">{research.reason}</pre>}
      {research.assessment_error && <pre className="mt-3 text-[11px] whitespace-pre-wrap break-words">{research.assessment_error}</pre>}
      {research.diagnostic && <pre className="mt-3 text-[11px] whitespace-pre-wrap break-words">{JSON.stringify(research.diagnostic, null, 2)}</pre>}
      </details>
    </div>
    {!compact && <details className="work-widget" aria-label="Questions de recherche">
      <summary className="work-link text-[12px]">Questions à établir · {research.questions.length}</summary>
      {research.questions.map((question) => {
        const claims = research.claims.filter((claim) => claim.question_id === question.id);
        return <div key={question.id} className="mt-4 text-[12px]">
          <p>{question.text}</p>
          <p className="work-muted mt-1">{claims.length ? [...new Set(claims.map((c) => verdicts[c.status]))].join(' · ') : 'À établir'}</p>
          <details className="mt-2"><summary className="work-link">Preuves attendues et fraîcheur</summary>
            <p className="mt-2 work-muted">{question.evidence_needed}</p><p className="mt-1 work-muted">{question.freshness}</p></details>
        </div>;
      })}
    </details>}
    {compact && <>
      {!!research.claims.length && <section className="work-widget" aria-label="Synthèse de recherche"><div className="work-eyebrow">Conclusions</div>{research.claims.slice(0, 2).map((claim) => <div key={claim.id} className="mt-3 text-[12px]"><span className="work-muted">{verdicts[claim.status]}</span><p className="mt-1 leading-relaxed">{claim.text}</p></div>)}</section>}
      {!!research.sources.length && <section className="work-widget" aria-label="Sources récentes"><div className="work-eyebrow">Sources · {read.length} lues / {research.sources.length} trouvées</div>{research.sources.slice(-3).map((source) => <div key={source.id} className="mt-3 text-[12px]"><p className="line-clamp-2 break-words">{source.acquisition?.title || source.title || source.url}</p><p className="work-muted text-[11px] mt-1">{source.status === 'read' ? 'Passages consultés' : source.status === 'inaccessible' ? 'Accès impossible' : 'Pas encore lue'}</p></div>)}</section>}
      {inspect && (research.sources.length > 0 || research.history.length > 0 || research.claims.length > 0) && <button className="work-secondary justify-center" onClick={inspect}>Examiner les sources et les preuves</button>}
      {!!research.history.length && <div className="px-2 text-[11px] work-muted" aria-label="Dernière action observée">{tools[research.history.at(-1)!.tool] || 'Dernière action'} · {research.history.at(-1)!.status === 'error' ? 'Non aboutie' : 'Terminée'}</div>}
    </>}
    {!compact && <>
    {!!research.claims.length && <section className="work-widget" aria-label="Conclusions sourcées">
      <div className="work-eyebrow">Conclusions et limites</div>
      <p className="text-[11px] mt-2 work-muted">Évaluation fondée sur les passages consultés, à la date de recherche.</p>
      {research.claims.map((claim) => <article key={claim.id} className="mt-5 text-[12px]">
        <span className="work-step-status" data-status={claim.status === 'supported' ? 'done' : 'failed'}>{verdicts[claim.status]}</span>
        <p className="mt-2">{claim.text}</p><p className="work-muted mt-2">{claim.basis}</p>
        {claim.scope === 'attributed_experience' && <p className="work-muted mt-2">Témoignage attribué · ne démontre pas un comportement général.</p>}
        {claim.limitations.map((limit, i) => <p key={i} className="mt-2" style={{ color: 'var(--warning)' }}>{limit}</p>)}
        <details className="mt-3"><summary className="work-link">Examiner les preuves et les contradictions</summary>
          {claim.evidence.map((link, i) => {
            const passage = research.passages.find((p) => p.id === link.passage_id);
            const citation = research.assessments.find((a) => a.claim_id === claim.id)?.citations.find((c) => c.passage_id === link.passage_id && c.relation === link.relation);
            const source = research.sources.find((s) => s.id === passage?.source_id);
            const href = source && publicLink(source.final_url || source.url);
            return <div key={`${link.passage_id}:${i}`} className="mt-3">
              <p className="work-muted">{link.relation === 'supports' ? 'Soutient' : link.relation === 'contradicts' ? 'Contredit' : 'Contexte'} · {link.passage_id}</p>
              {citation && <><blockquote className="mt-2 whitespace-pre-wrap">{citation.quote}</blockquote><p className="mt-2 work-muted">{citation.explanation}</p></>}
              {!citation && passage && <blockquote className="mt-2 whitespace-pre-wrap">{passage.text}</blockquote>}
              {href && <a className="work-link mt-2 break-all" href={href} target="_blank" rel="noreferrer">{source?.title || href}<ExternalLink size={12} /></a>}
            </div>;
          })}
        </details>
      </article>)}
    </section>}
    <section className="work-widget" aria-label="Sources consultées">
      <div className="work-eyebrow">Sources · {read.length} lues / {research.sources.length} trouvées</div>
      {!research.sources.length && <p className="text-[12px] mt-3 work-muted">Aucune source trouvée pour le moment.</p>}
      {research.sources.map((source) => {
        const assessment = assessed.find((a) => a.source_id === source.id);
        const href = publicLink(source.final_url || source.url);
        return <details key={source.id} className="mt-4 text-[12px]">
          <summary className="cursor-pointer break-words">{source.acquisition?.title || source.title || source.url}<span className="block mt-1 work-muted text-[11px]">{source.status === 'read' ? 'Lue' : source.status === 'inaccessible' ? 'Accès impossible' : 'Trouvée · non lue'} · {kinds[assessment?.kind || source.source_kind] || 'Non évaluée'}</span></summary>
          {href && <a className="work-link mt-3 break-all" href={href} target="_blank" rel="noreferrer">Ouvrir la source <ExternalLink size={12} /></a>}
          {source.consulted_at && <p className="mt-2 work-muted">Consultée le {new Date(source.consulted_at).toLocaleString('fr-FR')}</p>}
          {source.acquisition?.captured_at && <p className="mt-2 work-muted">Observation capturée le {new Date(source.acquisition.captured_at).toLocaleString('fr-FR')} · {source.acquisition.mode === 'browser' ? 'Rendu navigateur' : 'HTTP'}{source.acquisition.cache_hit ? ' · réutilisée depuis le cache' : ''}</p>}
          {source.truncated && <p className="mt-2 work-muted">Contexte partiel · certains blocs ne figurent pas dans la sélection.</p>}
          {source.acquisition?.status && access[source.acquisition.status] && <p className="mt-2" role="status">{access[source.acquisition.status]}</p>}
          {source.error && <p role="alert" className="mt-2">{source.error}</p>}
          {source.acquisition?.limitations?.map((limit, i) => <p key={`access:${i}`} className="work-muted mt-2">{limit}</p>)}
          {source.acquisition?.selection && <details className="mt-3" aria-label="Sélection du contexte">
            <summary className="work-link">Sections retenues et contexte omis</summary>
            <p className="mt-2 work-muted">{source.acquisition.selection.characters_selected}/{source.acquisition.selection.characters_available} caractères de l’index · {source.acquisition.selection.selected_group_ids.length}/{source.acquisition.selection.group_count} sections retenues</p>
            <p className="mt-2 work-muted">{source.acquisition.selection.coverage === 'complete' ? 'Index entièrement représenté' : 'Couverture partielle · les réserves hors sélection restent à examiner'} · {source.acquisition.selection.method === 'explicit-section-ids' ? 'Lecture de sections demandées' : source.acquisition.selection.method === 'complete-small-observation' ? 'Petit contenu conservé' : 'Classement lexical local'}</p>
            {!!source.acquisition.selection.partial_group_ids?.length && <p className="mt-2 work-muted">{source.acquisition.selection.partial_group_ids.length} section(s) partiellement représentée(s) par l’extraction principale.</p>}
            <ul className="mt-2 space-y-2">{source.acquisition.selection.catalog.filter((g) => !source.acquisition!.selection!.selected_group_ids.includes(g.id) || source.acquisition!.selection!.partial_group_ids?.includes(g.id)).map((g) => <li key={g.id} className="work-muted break-words">{g.context.join(' › ') || 'Sans titre'} · {g.characters} caractères</li>)}</ul>
            {source.acquisition.selection.catalog_truncated && <p className="mt-2 work-muted">Catalogue partiel · {source.acquisition.selection.omitted_group_count ?? source.acquisition.selection.omitted_group_ids.length} sections omises au total. Une lecture ciblée permet d’approfondir.</p>}
          </details>}
          {assessment && <><p className="mt-3 work-muted">{assessment.basis}</p>{assessment.limitations.map((item, i) => <p key={i} className="mt-2 work-muted">{item}</p>)}
            <p className="mt-2 work-muted">{assessment.suitability === 'suitable' ? 'Adaptée à la question selon la revue' : assessment.suitability === 'limited' ? 'Preuve limitée pour cette question' : 'Pertinence de la preuve non établie'} · groupe d’origine {research.assessments[0]?.origin_groups[source.id] || 'non établi'}</p>
            {!!assessment.origin_urls.length && <p className="mt-2 work-muted break-all">Origines citées : {assessment.origin_urls.join(' · ')}</p>}</>}
          <SourcePassages passages={research.passages.filter((p) => p.source_id === source.id)} />
        </details>;
      })}
    </section>
    <section className="work-widget" aria-label="Journal de recherche">
      <div className="flex justify-between gap-2 items-center"><span className="work-eyebrow">Actions observées</span><button className="work-link text-[11px]" aria-pressed={follow} onClick={() => setFollow(!follow)}>{follow ? 'Suivi activé' : 'Reprendre le suivi'}</button></div>
      <div ref={log} className="mt-3 max-h-52 overflow-y-auto" onScroll={(event) => { const el = event.currentTarget; if (el.scrollHeight - el.scrollTop - el.clientHeight > 40) setFollow(false); }}>
        {!research.history.length && <p className="text-[12px] work-muted">Aucune action terminée.</p>}
        {research.history.map((item) => <div key={item.index} className="mt-3 text-[12px]"><p>{tools[item.tool] || item.tool} · {item.status === 'error' ? 'Échec' : item.status === 'empty' ? 'Aucun résultat' : 'Terminé'}</p><p className="mt-1 work-muted">{item.error || item.rationale}</p></div>)}
      </div>
    </section>
    </>}
  </section>;
}

export function ResearchPanel({ run, compact = false, inspect }: { run: RunState; compact?: boolean; inspect?: () => void }) {
  return <div>{Object.entries(run.researches || {}).map(([id, research]) => <ResearchWork key={id} research={research} live={run.status === 'running'} compact={compact} inspect={inspect} />)}</div>;
}
