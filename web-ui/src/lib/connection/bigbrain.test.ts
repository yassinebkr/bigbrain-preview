import { describe, expect, it, vi } from 'vitest';
import { BigBrainConnection } from './bigbrain';

describe('session-scoped websocket replies', () => {
  it('does not render text or finish streaming for another conversation', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    conn.switchSession('sess-new');
    const message = vi.fn();
    const delta = vi.fn();
    const end = vi.fn();
    const activity = vi.fn();
    conn.on('onMessage', message);
    conn.on('onStreamDelta', delta);
    conn.on('onRunEnd', end);
    conn.on('onAgentActivity', activity);
    for (const event of ['chat.message', 'chat.delta', 'chat.done', 'task.failed']) {
      (conn as any)._handleFrame({ payload: { event, session_id: 'sess-old', text: 'old', delta: 'old' } });
    }
    expect(message).not.toHaveBeenCalled();
    expect(delta).not.toHaveBeenCalled();
    expect(end).not.toHaveBeenCalled();
    expect(activity).toHaveBeenCalledWith(expect.objectContaining({ type: 'task.failed' }));
    (conn as any)._handleFrame({ payload: { event: 'chat.message', session_id: 'sess-new', text: 'new reply' } });
    expect(message).toHaveBeenCalledWith(expect.objectContaining({ text: 'new reply' }));
  });
});
