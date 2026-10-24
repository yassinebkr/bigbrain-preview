import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it } from 'vitest';
import { researchUpdate, publicLink } from '@/lib/research';
import { surfaceRegistry } from '@/lib/morphable';
import { useAppStore, type RunState } from '@/store/appStore';
import { ResearchActivity, ResearchPanel } from './ResearchPanel';

function snapshot(overrides: Record<string, unknown> = {}) {
  return { schema_version: '1.0', research_id: 'research-1', revision: 1, objective: 'Question réelle', status: 'running',
    reason: null, assessment_error: null,
    questions: [{ id: 'q', text: 'Quel comportement ?', evidence_needed: 'Documentation versionnée', freshness: 'Version demandée' }],
    sources: [{ id: 's1', url: 'https://reference.test/api', title: '<script>bad()</script>', status: 'read',
      final_url: null, consulted_at: '2026-10-24T10:00:00Z', source_kind: 'unassessed', truncated: false, error: null }],
    claims: [], usage: {}, limits: { actions: 12, searches: 3, pages: 6, seconds: 90, tokens: 60000 },
    counts: { searches: 1, pages: 1 }, elapsed_seconds: 12, current_action: null, ...overrides };
}
const observation = { index: 1, status: 'ok', action: { tool: 'open', rationale: 'Lire la référence' },
  data: { passages: [{ id: 'p1', source_id: 's1', text: 'Texte réellement lu.' }] } };
const event = (type: string, detail: Record<string, unknown>) => ({ type, detail });
const run: RunState = { sessionId: 's', id: 'run', status: 'running', description: 'Recherche', startedAt: 1, files: [], steps: [] };

beforeEach(() => useAppStore.setState({ activeSessionKey: 's', activeRun: null, sessionRuns: {},
  runsById: {}, completedRuns: [], sessionProposals: {} }));

describe('durable research view', () => {
  it('collects actual passages once and ignores stale or duplicate snapshots', () => {
    const first = researchUpdate(snapshot(), undefined, observation)!;
    expect(first.passages[0].text).toBe('Texte réellement lu.');
    expect(researchUpdate(snapshot(), first, observation)).toBe(first);
    const terminal = researchUpdate(snapshot({ revision: 3, status: 'completed' }), first)!;
    expect(researchUpdate(snapshot({ revision: 4 }), terminal)).toBe(terminal);
    expect(terminal.history).toHaveLength(1);
  });

  it('rejects invalid payloads and unsafe links', () => {
    expect(researchUpdate({ schema_version: 'unknown' })).toBeUndefined();
    expect(publicLink('javascript:alert(1)')).toBeUndefined();
    expect(publicLink('https://user:secret@host.test')).toBeUndefined();
    expect(publicLink('https://reference.test/api')).toBe('https://reference.test/api');
  });

  it('keeps concurrent research on its exact run and conversation', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(event('task.received', { task_id: 'run', session_id: 's' }));
    s.applyRunEvent(event('task.received', { task_id: 'other', session_id: 'foreign' }));
    s.applyRunEvent(event('task.progress', { task_id: 'run', session_id: 's', subtask_id: 'step', research: snapshot(), observation }));
    expect(useAppStore.getState().runsById.run.researches?.['step:research-1'].passages).toHaveLength(1);
    expect(useAppStore.getState().runsById.other.researches).toBeUndefined();
    s.applyRunEvent(event('task.progress', { task_id: 'run', session_id: 'foreign', subtask_id: 'step', research: snapshot({ revision: 2 }) }));
    expect(useAppStore.getState().runsById.run.researches?.['step:research-1'].revision).toBe(1);
  });

  it('keeps final evidence received after Stop without resurrecting work', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(event('task.received', { task_id: 'run', session_id: 's' }));
    s.applyRunEvent(event('task.progress', { task_id: 'run', session_id: 's', subtask_id: 'step', research: snapshot() }));
    s.applyRunEvent(event('task.cancelled', { task_id: 'run', session_id: 's' }));
    s.applyRunEvent(event('task.progress', { task_id: 'run', session_id: 's', subtask_id: 'step',
      research: snapshot({ revision: 5, status: 'cancelled', passages: observation.data.passages }) }));
    const done = useAppStore.getState().completedRuns[0];
    expect(done.status).toBe('cancelled');
    expect(done.researches?.['step:research-1'].passages).toHaveLength(1);
    expect(useAppStore.getState().runsById.run).toBeUndefined();
    expect(renderToStaticMarkup(<ResearchPanel run={done} />)).not.toContain('animate-spin');
  });

  it('preserves distinct attempts of the same subtask', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(event('task.received', { task_id: 'run', session_id: 's' }));
    for (const id of ['first', 'retry']) s.applyRunEvent(event('task.progress', {
      task_id: 'run', session_id: 's', subtask_id: 'step', research: snapshot({ research_id: id }) }));
    expect(Object.keys(useAppStore.getState().runsById.run.researches || {})).toHaveLength(2);
  });

  it('restores terminal passages from a checkpoint without network or execution', () => {
    const restored = researchUpdate(JSON.parse(JSON.stringify(snapshot({ status: 'completed', revision: 12,
      passages: observation.data.passages }))))!;
    const html = renderToStaticMarkup(<ResearchPanel run={{ ...run, status: 'done', researches: { step: restored } }} />);
    expect(html).toContain('Texte réellement lu.');
    expect(html).toContain('Recherche terminée');
    expect(html).not.toContain('animate-spin');
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
    expect(surfaceRegistry('s', [{ ...run, researches: { step: restored } }]).map((s) => s.kind)).toEqual(['activity', 'research']);
  });

  it('marks a restored interrupted run instead of claiming live progress', () => {
    const restored = researchUpdate(snapshot())!;
    const html = renderToStaticMarkup(<ResearchPanel run={{ ...run, status: 'failed', researches: { step: restored } }} />);
    expect(html).toContain('Recherche interrompue');
    expect(html).not.toContain('animate-spin');
  });

  it('shows uncertainty and the difference between found and read sources', () => {
    const data = snapshot({ claims: [{ id: 'c', question_id: 'q', text: 'Un témoignage seulement', status: 'unverified',
      basis: 'Aucune corroboration indépendante', evidence: [], limitations: ['Pas de causalité démontrée'], scope: 'attributed_experience' }] });
    const html = renderToStaticMarkup(<ResearchPanel run={{ ...run, researches: { step: researchUpdate(data)! } }} />);
    expect(html).toContain('Non vérifié');
    expect(html).toContain('Pas de causalité démontrée');
    expect(html).toContain('ne démontre pas un comportement général');
    expect(html).toContain('coût inconnu');
  });

  it('keeps the overview distinct from the evidence inspector and the objective out of headings', () => {
    const objective = 'A long original request '.repeat(40);
    const data = researchUpdate(snapshot({ objective }))!;
    const overview = renderToStaticMarkup(<ResearchPanel run={{ ...run, researches: { step: data } }} compact inspect={() => {}} />);
    expect(overview).not.toMatch(/<h3[^>]*>[^<]*A long/);
    expect(overview).toContain('<summary class="work-link">Demande initiale</summary>');
    expect(overview).not.toContain('Questions à établir');
    expect(overview).not.toContain('Journal de recherche');
    expect(overview).toContain('Examiner les sources et les preuves');
    const full = renderToStaticMarkup(<ResearchPanel run={{ ...run, researches: { step: data } }} />);
    expect(full).toContain('Questions à établir');
    expect(full).toContain('Journal de recherche');
  });

  it('keeps raw legacy errors inside a closed diagnostic disclosure', () => {
    const data = researchUpdate(snapshot({ sources: [], status: 'partial', reason: 'ValidationError input_value=legacy-private-marker errors.pydantic.dev',
      diagnostic: { contract: 'Action', code: 'json_invalid', errors: [{ type: 'json_invalid', field: '' }] } }))!;
    const html = renderToStaticMarkup(<ResearchPanel run={{ ...run, status: 'failed', researches: { step: data } }} compact />);
    expect(html).toContain('Le modèle a renvoyé un format de réponse invalide.');
    expect(html).not.toContain('aria-label="Questions de recherche"');
    expect(html).toMatch(/<details[^>]*><summary[^>]*>Usage et diagnostic<\/summary>[\s\S]*legacy-private-marker[\s\S]*<\/details>/);
    expect(html).not.toContain('<details open');
  });

  it('shows the actual acquisition phase in the default overview and research panel', () => {
    const data = researchUpdate(snapshot({ activity: { stage: 'research_acquisition', phase: 'selecting_context', source_id: 's1', mode: 'http' },
      limits: { actions: 12, searches: 3, pages: 6, browsers: 2, seconds: 90, tokens: 60000 }, counts: { searches: 1, pages: 1, browsers: 1 } }))!;
    const html = renderToStaticMarkup(<ResearchPanel run={{ ...run, researches: { step: data } }} />);
    expect(html).toContain('Sélection des sections selon la question');
    expect(html).toContain('1/2 lectures navigateur tentées');
    const overview = renderToStaticMarkup(<ResearchActivity research={data} live inspect={() => {}} />);
    expect(overview).toContain('Sélection des sections selon la question');
    expect(overview).toContain('Suivre la recherche et ses preuves');
    const stopped = renderToStaticMarkup(<ResearchActivity research={data} live={false} />);
    expect(stopped).not.toContain('animate-spin');
    expect(stopped).not.toContain('Sélection des sections selon la question');
  });

  it('retains source acquisition, section omissions, cache and restrictions without artifact payloads', () => {
    const source = { ...snapshot().sources[0], acquisition: { title: 'Référence observée', mode: 'browser', status: 'needs_context',
      captured_at: '2026-10-24T10:00:00Z', cache_hit: true, limitations: ['Capture bornée ; changements ultérieurs inconnus'],
      raw_artifact: { secret: 'internal-marker' }, selection: { status: 'needs_context', method: 'local-bm25-sections', coverage: 'partial',
        characters_selected: 0, characters_available: 9000, group_count: 80, selected_group_ids: [], omitted_group_ids: ['g1'],
        omitted_group_count: 80, catalog_truncated: true, catalog: [{ id: 'g1', context: ['Conditions de mesure'], characters: 240 }] } } };
    const data = researchUpdate(snapshot({ sources: [source] }))!;
    const html = renderToStaticMarkup(<ResearchPanel run={{ ...run, researches: { step: data } }} />);
    expect(html).toContain('Référence observée');
    expect(html).toContain('réutilisée depuis le cache');
    expect(html).toContain('Rendu navigateur');
    expect(html).toContain('Conditions de mesure');
    expect(html).toContain('80 sections omises');
    expect(html).toContain('Sélection insuffisante');
    expect(html).toContain('Capture bornée');
    expect(JSON.stringify(data)).not.toContain('internal-marker');
  });

  it('accepts more than sixty observed passages and restores the terminal action history', () => {
    const passages = Array.from({ length: 125 }, (_, i) => ({ id: `p${i}`, source_id: 's1', text: `Observed block ${i}`, review_only: i > 60 }));
    const data = researchUpdate(snapshot({ status: 'partial', revision: 30, passages,
      history: [{ index: 4, tool: 'open', rationale: 'Read scope', status: 'error', error: 'Read budget exhausted' }] }))!;
    expect(data.passages).toHaveLength(125);
    expect(data.history[0].error).toBe('Read budget exhausted');
    const html = renderToStaticMarkup(<ResearchPanel run={{ ...run, status: 'failed', researches: { step: data } }} />);
    expect(html).toContain('105 restants');
    expect(html).not.toContain('Observed block 124');
    expect(html).toContain('Read budget exhausted');
  });

  it('registers real review supplements before completion and deduplicates replay', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(event('task.received', { task_id: 'run', session_id: 's' }));
    const detail = { task_id: 'run', session_id: 's', subtask_id: 'step', stage: 'research_review_evidence',
      research: snapshot({ revision: 8 }), passages: [{ id: 'review-p1', source_id: 's1', text: 'Distant observed reservation', review_only: true }] };
    s.applyRunEvent(event('task.progress', detail));
    s.applyRunEvent(event('task.progress', detail));
    const view = useAppStore.getState().runsById.run.researches!['step:research-1'];
    expect(view.passages).toHaveLength(1);
    expect(view.passages[0].review_only).toBe(true);
    expect(renderToStaticMarkup(<ResearchPanel run={{ ...run, researches: { step: view } }} />)).toContain('Observation complémentaire de la revue');
  });

  it('keeps acquisition updates isolated while switching conversations and rehydrates from serialized events', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(event('task.received', { task_id: 'run', session_id: 's' }));
    useAppStore.setState({ activeSessionKey: 'foreign', activeRun: null });
    const frame = event('task.progress', { task_id: 'run', session_id: 's', subtask_id: 'step', research: snapshot({
      activity: { stage: 'research_acquisition', phase: 'browser_request', source_id: 's1', request_index: 3 } }) });
    s.applyRunEvent(JSON.parse(JSON.stringify(frame)));
    expect(useAppStore.getState().activeRun).toBeNull();
    const data = useAppStore.getState().runsById.run.researches!['step:research-1'];
    expect(data.activity?.request_index).toBe(3);
    expect(data.activity?.phase).toBe('browser_request');
    expect(useAppStore.getState().sessionRuns.foreign).toBeUndefined();
  });
});
