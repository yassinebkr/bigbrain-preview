import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SurfaceContent } from './ContextWorkspace';
import type { RunState } from '@/store/appStore';
import { surfaceRegistry, workspaceTabs } from '@/lib/morphable';

const run: RunState = { id: 'real', sessionId: 's', description: 'Run from bus', status: 'failed', startedAt: 1, files: [], steps: [{ id: 'step', brain: 'web_app_brain_0', description: 'Build', status: 'failed', liveOutput: '<script>unsafe()</script>' }], error: 'Actual build error' };

describe('bounded contextual catalog', () => {
  it('restores retained CAD routes into one selected piece tab', () => {
    const cadRun: RunState = { ...run, cad: {
      schema_version:'1.0', document_id:'a'.repeat(32), title:'Plate', sequence:1,
      status:'failed', elapsed_seconds:1, snapshot:null, diagnostic:'Interrupted',
    }, verification:{runId:'cad-checks', verdict:'inconclusive', stages:[]} };
    const surfaces = surfaceRegistry(run.sessionId, [cadRun]);
    const retained = surfaces.find(surface => surface.kind === 'cad');
    expect(retained).toBeDefined();
    const tabs = workspaceTabs(surfaces, retained);
    expect(tabs.map(tab => tab.label)).toEqual(['Pièce', 'Vérifications']);
    expect(tabs.filter(tab => tab.selected).map(tab => tab.label)).toEqual(['Pièce']);
  });
  it('does not animate stale running stages in restored failed runs', () => {
    const html = renderToStaticMarkup(<SurfaceContent surface={{ id: 'activity', kind: 'activity', run: { ...run, steps: [{ id: 'planning', brain: 'planner', description: 'Architecture', status: 'running' }] } }} />);
    expect(html).not.toContain('animate-spin');
    expect(html).not.toContain('En cours');
    expect(html).toContain('Échec');
    expect(html).toContain('Architecture');
  });
  it('renders actual agent attribution/error and escapes output, without invented evidence', () => {
    const html = renderToStaticMarkup(<SurfaceContent surface={{ id: 'activity', kind: 'activity', run }} />);
    expect(html).toContain('web_app_brain_0');
    expect(html).toContain('Actual build error');
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('Verdict');
    expect(html).not.toContain('Approve');
    expect(html).not.toContain('<iframe');
  });
  it('does not mislabel failed verification as success', () => {
    const html = renderToStaticMarkup(<SurfaceContent surface={{ id: 'proof', kind: 'verification', run: { ...run, verification: { runId: 'evidence', verdict: 'failed', stages: [{ name: 'browser', status: 'failed' }] } } }} />);
    expect(html).toContain('failed');
    expect(html).toContain('browser');
    expect(html).not.toContain('passed');
  });
});
