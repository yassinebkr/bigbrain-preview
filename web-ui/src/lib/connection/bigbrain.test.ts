import { describe, expect, it, vi } from 'vitest';
import { BigBrainConnection } from './bigbrain';

describe('session-scoped websocket replies', () => {
  it('ends the pending reply on current-session user Stop only', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    conn.switchSession('s');
    const end = vi.fn();
    conn.on('onRunEnd', end);
    for (const payload of [
      { event: 'task.cancelled', session_id: 'other', mode: 'user' },
      { event: 'task.cancelled', session_id: 's', mode: 'user', task_id: 'worker-run' },
    ]) (conn as any)._handleFrame({ payload });
    expect(end).not.toHaveBeenCalled();
    (conn as any)._handleFrame({ payload: { event: 'task.cancelled', session_id: 's', mode: 'user' } });
    expect(end).toHaveBeenCalledOnce();
  });
  it('ends waiting even when a terminal assistant message is empty', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    conn.switchSession('s');
    const end = vi.fn();
    conn.on('onRunEnd', end);
    (conn as any)._handleFrame({ type: 'event', payload: { event: 'chat.message', session_id: 's', text: '' } });
    expect(end).toHaveBeenCalledOnce();
  });
  it('reports a missing socket instead of pretending to send', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    const error = vi.fn();
    const status = vi.fn();
    conn.on('onSendError', error);
    conn.on('onMessageStatus', status);
    const id = conn.send('Retry', [], 'sess-live');
    expect(error).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('pas été envoyé') }), id);
    expect(status).toHaveBeenLastCalledWith(id, 'failed');
  });
  it('surfaces a rejected delivery so the app can stop its waiting indicator', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    const error = vi.fn();
    conn.on('onSendError', error);
    (conn as any)._handleFrame({ type: 'message.status', payload: { messageId: 'm', status: 'failed' } });
    expect(error).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('refusé') }), 'm');
  });
  it('restores replayed widget suggestions without ending a reply or executing anything', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    conn.switchSession('s');
    const activity = vi.fn();
    const end = vi.fn();
    conn.on('onAgentActivity', activity);
    conn.on('onRunEnd', end);
    (conn as any)._handleFrame({ type: 'event', _replay: true, source: 'orchestrator_default', payload: {
      event: 'workspace.proposal', task_id: 'r', session_id: 's', producer: 'architect',
      proposal: { version: 1, revision: 1, widgets: ['files'] },
    } });
    expect(activity).toHaveBeenCalledWith(expect.objectContaining({ type: 'workspace.proposal' }));
    expect(end).not.toHaveBeenCalled();
  });
  it('does not finalize front-brain streaming when a worker finishes', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    conn.switchSession('sess-live');
    const end = vi.fn();
    conn.on('onRunEnd', end);
    (conn as any)._handleFrame({ type: 'event', payload: {
      event: 'task.complete', task_id: 'board', session_id: 'sess-live',
    } });
    expect(end).not.toHaveBeenCalled();
  });
  it('restores transcript and durable run state for the exact requested session', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    conn.switchSession('sess-running');
    let answer!: (frame: any) => void;
    (conn as any)._request = (_method: string, callback: (frame: any) => void) => { answer = callback; return 'req-history'; };
    const catchUp = vi.fn();
    const activity = vi.fn();
    conn.on('onResumeCatchUp', catchUp);
    conn.on('onAgentActivity', activity);
    conn.loadHistory();
    answer({ payload: { sessionId: 'sess-running', as_of: 20,
      messages: [{ id: 'm1', role: 'assistant', text: 'Projet terminé', timestamp: 10 }],
      activities: [{ timestamp: 11, payload: { event: 'task.complete', task_id: 'web', session_id: 'sess-running' } }],
    } });
    expect(catchUp).toHaveBeenCalledWith([
      expect.objectContaining({ content: 'Projet terminé', timestamp: 10000 }),
    ], 'sess-running', 20000);
    expect(activity).toHaveBeenCalledWith(expect.objectContaining({ type: 'task.complete', ts: 11000 }));
  });

  it('ignores late catch-up when the user changed conversations', () => {
    const conn = new BigBrainConnection({ wsUrl: 'ws://localhost/ws' });
    conn.switchSession('sess-old');
    let answer!: (frame: any) => void;
    (conn as any)._request = (_method: string, callback: (frame: any) => void) => { answer = callback; return 'req-history'; };
    const catchUp = vi.fn();
    conn.on('onResumeCatchUp', catchUp);
    conn.loadHistory();
    conn.switchSession('sess-new');
    answer({ payload: { sessionId: 'sess-old', messages: [] } });
    expect(catchUp).not.toHaveBeenCalled();
  });

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
