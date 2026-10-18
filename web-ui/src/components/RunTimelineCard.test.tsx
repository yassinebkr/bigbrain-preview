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

  it('shows preview and project controls even when docked/collapsed', () => {
    const html = renderToStaticMarkup(<RunTimelineCard run={run} />);
    expect(html).toContain('<iframe');
    expect(html).toContain('src="http://127.0.0.1:3200"');
    expect(html).toContain('aria-label="Open project"');
    expect(html).toContain('aria-label="Run project"');
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
});
