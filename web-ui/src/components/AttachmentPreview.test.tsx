import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { AttachmentPreview } from './AttachmentPreview';
import { CadDesignBrief } from './CadDesignBrief';
import { useAppStore } from '@/store/appStore';

const image = { id: 'att-012345abcdef', name: 'drawing.png', type: 'image/png', size: 12 };
describe('drawing sources and clarification dossier', () => {
  it('renders a persisted thumbnail with an enlargement action', () => {
    const html = renderToStaticMarkup(<AttachmentPreview attachment={image} />);
    expect(html).toContain('/api/attachments/att-012345abcdef');
    expect(html).toContain('Agrandir drawing.png');
    expect(html).toContain('alt="drawing.png"');
  });
  it('keeps non-images as filenames', () => {
    expect(renderToStaticMarkup(<AttachmentPreview attachment={{ ...image, type: 'application/pdf' }} />)).not.toContain('<img');
  });
  it('renders the acquired dimensions, unknowns, source and exact clarification', () => {
    const html = renderToStaticMarkup(<CadDesignBrief brief={{ revision: 2, status: 'clarifying', sources: [image],
      question: 'Quelle hauteur ?', exchanges: [{ user: 'Largeur 3 mm', assistant: 'Quelle hauteur ?' }],
      drawing: { title: 'Support', issues: [], dimensions: [
        { id: 'w', label: 'Largeur', value: 3, unit: 'mm', origin: 'user' },
        { id: 'h', label: 'Hauteur', value: null, unit: 'mm', origin: 'unresolved' }] } }} />);
    expect(html).toContain('Quelle hauteur ?');
    expect(html).toContain('Précisée par toi');
    expect(html).toContain('À préciser');
    expect(html).toContain('Largeur 3 mm');
    expect(html).toContain('/api/attachments/att-012345abcdef');
  });
  it('scopes live dossiers to their conversation and ignores stale revisions', () => {
    const store = useAppStore.getState();
    useAppStore.setState({ activeSessionKey: 'visible', cadBriefs: {} });
    store.applyRunEvent({ type: 'cad.context.updated', detail: { session_id: 'background', context: { revision: 2, status: 'clarifying' } } });
    store.applyRunEvent({ type: 'cad.context.updated', detail: { session_id: 'background', context: { revision: 1 } } });
    expect(useAppStore.getState().cadBriefs.visible).toBeUndefined();
    expect(useAppStore.getState().cadBriefs.background?.revision).toBe(2);
  });
  it('keeps a failed attachment upload from reaching inference', async () => {
    const send = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const attachment = { ...image, file: new File(['drawing'], 'drawing.png', { type: 'image/png' }) };
    useAppStore.setState({ activeSessionKey: 'upload-session', view: 'chat', messages: [],
      connectionStatus: 'connected', connection: { send } as never,
      inputText: 'Create this part', attachments: [attachment] });
    useAppStore.getState().sendMessage();
    await vi.waitFor(() => expect(useAppStore.getState().historyError).toContain('message n’a pas été envoyé'));
    expect(send).not.toHaveBeenCalled();
    expect(useAppStore.getState().inputText).toBe('Create this part');
    expect(useAppStore.getState().attachments).toHaveLength(1);
    expect(useAppStore.getState().isStreaming).toBe(false);
    vi.unstubAllGlobals();
  });
});
