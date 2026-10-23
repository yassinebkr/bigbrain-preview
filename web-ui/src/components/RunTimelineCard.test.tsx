import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RunTimelineCard } from './RunTimelineCard';
import type { RunState } from '@/store/appStore';

describe('verified web delivery card', () => {
  const run: RunState = {
    id: 'excel-plan', sessionId: 'excel-session', description: 'Excel',
    status: 'done', startedAt: 1, finishedAt: 2, steps: [], files: [],
    projectName: 'excel', projectPath: 'sandbox/excel', entryPoint: 'index.html',
    deliverableType: 'web_app', runnable: true, previewUrl: 'http://127.0.0.1:3200',
  };

  it('offers the result without starting a preview in the chat', () => {
    const html = renderToStaticMarkup(<RunTimelineCard run={run} />);
    expect(html).toContain('Afficher le résultat');
    expect(html).not.toContain('src="http://127.0.0.1:3200"');
    expect(html).toContain('aria-label="Open project"');
    expect(html).not.toContain('aria-label="Run project"');
    expect(html).not.toContain('No verified runnable entry point');
  });

  it('does not offer Run on an unsuccessful validation', () => {
    const html = renderToStaticMarkup(<RunTimelineCard run={{
      ...run, status: 'failed', runnable: false, previewUrl: undefined,
      error: 'tests/acceptance.json: invalid schema',
    }} />);
    expect(html).not.toContain('<iframe');
    expect(html).not.toContain('aria-label="Run project"');
    expect(html).toContain('Run failed');
    expect(html).toContain('tests/acceptance.json: invalid schema');
  });

  it('keeps the chat compact when the result belongs to the right surface', () => {
    const html = renderToStaticMarkup(<RunTimelineCard run={run} />);
    expect(html).toContain('Afficher le résultat');
    expect(html).not.toContain('<iframe');
    expect(html).not.toContain('Ouverture de l’aperçu');
    expect(html).not.toContain('aria-label="Run project"');
  });

  it('labels incomplete delivery and blocks launch even with stale success metadata', () => {
    const html = renderToStaticMarkup(<RunTimelineCard run={{ ...run,
      deliveryStatus: 'incomplete', deliverableType: 'python', entryPoint: 'main.py',
    }} />);
    expect(html).toContain('Projet incomplet');
    expect(html).toContain('non validé');
    expect(html).not.toContain('Run complete');
    expect(html).not.toContain('aria-label="Run project"');
    expect(html).not.toContain('Afficher le résultat');
  });

  it('opens the taskboard, never a stale selected project, for board results', () => {
    const html = renderToStaticMarkup(<RunTimelineCard run={{ ...run,
      resultKind: 'taskboard', steps: [{ id: 'board', brain: 'taskboard', description: 'Add task', status: 'done' }],
    }} />);
    expect(html).toContain('aria-label="Open taskboard"');
    expect(html).not.toContain('aria-label="Open project"');
    expect(html).not.toContain('aria-label="Run project"');
    expect(html).not.toContain('<iframe');
  });
});
