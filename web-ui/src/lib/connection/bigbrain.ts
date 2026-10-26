// BigBrain adapter — speaks the BigBrain web server's WS protocol
// (docs/WEBUI-APLOT-PORT.md, "Frames BigBrain"). Same public surface and
// callbacks contract as the Scratchy adapter, so the store and App are
// unchanged.
//
// Protocol summary:
//  - On connect the server sends: welcome → focus.initial → system.status
//    → replayed frames (marked `_replay: true`).
//  - chat.send (payload {text, messageId}) → server acks
//    message.status (queued → sent) and routes one user_message task to
//    the front brain; replies arrive as chat.message event frames.
//  - ping → pong (app-level keepalive).
//  - req {method: 'chat.history', id} → resp {id, payload: {messages}}.

import type { ConnectionCallbacks, ConnectionLike } from './types';

const KEEPALIVE_MS = 25_000;
const MAX_RECONNECT_ATTEMPTS = 20;
const HISTORY_LIMIT = 100;

export class BigBrainConnection implements ConnectionLike {
  sessionKey = 'bigbrain:main';

  private ws: WebSocket | null = null;
  private callbacks: ConnectionCallbacks = {};
  private connected = false;
  private reconnectAttempts = 0;
  private keepaliveTimer: ReturnType<typeof setInterval> | null = null;
  private pongReceived = true;
  private wsUrl: string;
  private messageIdCounter = 0;
  private requestIdCounter = 0;
  private pendingRequests: Record<string, (frame: any) => void> = {};

  constructor(config?: { wsUrl?: string }) {
    if (config?.wsUrl) {
      this.wsUrl = config.wsUrl;
    } else {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.wsUrl = `${proto}//${location.host}/ws`;
    }
  }

  on<K extends keyof ConnectionCallbacks>(event: K, callback: ConnectionCallbacks[K]): void {
    this.callbacks[event] = callback as any;
  }

  connect(): void {
    if (this.ws) {
      try { this.ws.close(); } catch (e) { /* already closed */ }
      this.ws = null;
    }
    this.connected = false;
    this._updateStatus('connecting');

    this.ws = new WebSocket(this.wsUrl);
    this.ws.onopen = () => {
      // The server sends the welcome frame on connect; _handleFrame marks
      // the handshake complete when it arrives.
    };
    this.ws.onmessage = (event) => this._onMessage(event);
    this.ws.onclose = () => this._onClose();
    this.ws.onerror = () => { /* onclose follows */ };
  }

  disconnect(): void {
    this._stopKeepalive();
    this.reconnectAttempts = MAX_RECONNECT_ATTEMPTS; // no auto-reconnect
    if (this.ws) {
      try { this.ws.close(); } catch (e) { /* ignore */ }
      this.ws = null;
    }
    this.connected = false;
    this._updateStatus('disconnected');
  }

  forceReconnect(): void {
    this.reconnectAttempts = 0;
    this.connect();
  }

  send(text: string, attachments?: any[], sessionId?: string, navigationProject?: string | null): string {
    this.messageIdCounter += 1;
    const messageId = `msg-${Date.now()}-${this.messageIdCounter}`;
    this._emitStatus(messageId, 'sending');
    try {
      if (!this.ws || this.ws.readyState !== 1) throw new Error('Connexion au serveur indisponible. Le message n’a pas été envoyé.');
      this.ws.send(JSON.stringify({
        type: 'chat.send',
        payload: {
          text,
          messageId,
          sessionId,
          navigationProject,
          // Uploaded attachment refs ({id, name, type}) — recorded in
          // persistent memory by the front brain.
          attachments: (attachments || []).filter((a) => a && a.id),
        },
      }));
    } catch (e) {
      this.callbacks.onSendError?.({ message: String(e) }, messageId);
      this._emitStatus(messageId, 'failed');
      return messageId;
    }
    // 'queued' → 'sent' arrive as message.status frames from the server.
    return messageId;
  }

  listSessions(callback: (sessions: any[]) => void): void {
    this._request('sessions.list', (frame) => {
      for (const sessionId of frame.payload?.deletedSessionIds || []) {
        this.callbacks.onSessionChanged?.({ sessionId, deleted: true });
      }
      callback(frame.payload?.sessions || []);
    });
  }

  createSession(callback: (session: any) => void): void {
    this._request('sessions.create', (frame) => {
      callback(frame.payload?.session);
    });
  }

  deleteSession(sessionId: string): Promise<void> {
    return this._mutateSession('sessions.delete', { sessionId });
  }

  renameSession(sessionId: string, title: string): Promise<void> {
    return this._mutateSession('sessions.rename', { sessionId, title });
  }

  private _mutateSession(method: string, params: Record<string, string>): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (id) delete this.pendingRequests[id];
        reject(new Error('Le serveur ne répond pas. Vérifie la connexion puis réessaie.'));
      }, 20000);
      const id = this._request(method, (frame) => {
        clearTimeout(timer);
        if (frame.error) reject(new Error(String(frame.error)));
        else resolve();
      }, params);
      if (!id) { clearTimeout(timer); reject(new Error('Connexion au serveur indisponible.')); }
    });
  }

  cancel(): void {
    try {
      this.ws?.send(JSON.stringify({ type: 'chat.cancel', payload: { sessionId: this.sessionKey } }));
    } catch (e) { /* best effort */ }
  }

  loadHistory(callback?: (frame: any) => void, sessionId?: string): void {
    sessionId ||= this.sessionKey.startsWith('sess-') ? this.sessionKey : undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const id = this._request('chat.history', (frame) => {
      clearTimeout(timer);
      // Server entries: {id, role, text, timestamp}. Normalize to the
      // gateway shape the panels expect ({content} strings).
      const messages = (frame.payload?.messages || [])
        .slice(-HISTORY_LIMIT)
        .map((m: any) => ({
          id: m.id,
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.text,
          timestamp: typeof m.timestamp === 'number'
            ? m.timestamp * 1000
            : Date.parse(m.timestamp) || Date.now(),
        }));
      const responseSession = frame.payload?.sessionId || sessionId;
      const asOf = typeof frame.payload?.as_of === 'number' ? frame.payload.as_of * 1000 : undefined;
      if (frame.error && responseSession === this.sessionKey) {
        this.callbacks.onHistoryError?.('Impossible de restaurer cette conversation. Réessaie la connexion.', responseSession);
      }
      callback?.({ ok: !frame.error && !!frame.payload, payload: { messages, asOf } });
      // Also surface as catch-up so App can wire it later.
      if (responseSession === this.sessionKey && !frame.error) {
        this.callbacks.onResumeCatchUp?.(messages, responseSession, asOf);
        for (const activity of frame.payload?.activities || []) {
          if (activity.payload?.session_id !== responseSession) continue;
          this.callbacks.onAgentActivity?.({ type: activity.payload.event,
            detail: activity.payload, ts: activity.timestamp * 1000 });
        }
      }
    }, { sessionId });
    if (!id) {
      callback?.({ ok: false, payload: { messages: [] } });
    } else {
      timer = setTimeout(() => {
        const pending = this.pendingRequests[id];
        if (!pending) return;
        delete this.pendingRequests[id];
        pending({ error: 'History timeout' });
      }, 20000);
    }
  }

  switchSession(_newSessionKey: string): void {
    // BigBrain runs a single conversation with the front brain.
    this.sessionKey = _newSessionKey;
  }

  checkHealth(callback: (alive: boolean) => void, timeoutMs = 3000): void {
    if (!this.connected || !this.ws) {
      callback(false);
      return;
    }
    const timer = setTimeout(() => callback(false), timeoutMs);
    const prevPong = this.callbacks.onStatusChange;
    const id = this._request('__health', (frame) => {
      clearTimeout(timer);
      if (prevPong) this.callbacks.onStatusChange = prevPong;
      callback(frame.type === 'pong' || frame.error === undefined);
    });
    if (!id) callback(false);
  }

  // ── internals ──────────────────────────────────────────────────

  private _request(method: string, onResponse: (frame: any) => void,
                   params?: Record<string, any>): string | null {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return null;
    this.requestIdCounter += 1;
    const id = `req-${this.requestIdCounter}`;
    this.pendingRequests[id] = onResponse;
    if (method === '__health') {
      this.ws.send(JSON.stringify({ type: 'ping' }));
      // pong frames resolve every pending '__health' request.
      (this as any)._healthId = id;
    } else {
      this.ws.send(JSON.stringify({ type: 'req', id, method, params }));
    }
    return id;
  }

  private _onMessage(event: MessageEvent): void {
    let frame: any;
    try {
      frame = JSON.parse(event.data);
    } catch (e) {
      return; // non-JSON noise: ignore
    }
    this._handleFrame(frame);
  }

  private _handleFrame(frame: any): void {
    if (frame.type === 'session.changed') {
      this.callbacks.onSessionChanged?.(frame.payload);
      return;
    }
    // req/res resolution first.
    if (frame.type === 'resp' && frame.id && this.pendingRequests[frame.id]) {
      const cb = this.pendingRequests[frame.id];
      delete this.pendingRequests[frame.id];
      cb(frame);
      return;
    }
    if (frame.type === 'pong') {
      this.pongReceived = true;
      const healthId = (this as any)._healthId;
      if (healthId && this.pendingRequests[healthId]) {
        const cb = this.pendingRequests[healthId];
        delete this.pendingRequests[healthId];
        (this as any)._healthId = null;
        cb({ type: 'pong' });
      }
      return;
    }
    if (frame.type === 'welcome') {
      this.connected = true;
      this.reconnectAttempts = 0;
      this._updateStatus('connected');
      this._startKeepalive();
      // Catch up on history (the front brain's past replies).
      if (this.callbacks.onResumeCatchUp || this._historyWanted) {
        this.loadHistory();
      }
      return;
    }
    if (frame.type === 'message.status') {
      const { messageId, status } = frame.payload || {};
      if (messageId) this._emitStatus(messageId, status);
      if (status === 'failed') this.callbacks.onSendError?.({ message: 'Le serveur a refusé l’envoi du message.' }, messageId);
      if (status === 'sent') this.callbacks.onQueueDrained?.();
      return;
    }

    // Bus frames: envelope {type, source, target, payload: {event, ...}}.
    const payload = frame.payload || {};
    const event = payload.event;
    const isReplay = frame._replay === true;

    // Replayed frames are HISTORY (buffered from a previous session). They
    // must never drive live state — a replayed brain.started used to turn
    // on the typing indicator and 'working' pills forever. The chat
    // transcript on reconnect comes from loadHistory, not from replay.
    // EXCEPTION: a replayed contracts.proposal is still PENDING live
    // state (the plan waits for the user) — the card must come back.
    const replayableLiveState = new Set([
      'contracts.proposal', 'task.routing', 'task.received',
      'subtask.started',
      'workspace.proposal',
    ]);
    if (isReplay && !replayableLiveState.has(event)) return;

    // Text callbacks mutate the visible transcript, unlike scoped runs.
    const isCurrentSession = !payload.session_id || payload.session_id === this.sessionKey;
    if (event?.startsWith('chat.') && !isCurrentSession) return;

    if (frame.type === 'progress' && !isReplay) {
      this.callbacks.onAgentActivity?.({ type: 'task.progress',
        detail: { ...payload, brain: frame.source } });
      return;
    }

    if (event === 'chat.delta') {
      this.callbacks.onStreamDelta?.({
        text: payload.delta || '',
        role: 'assistant',
        source: frame.source || 'bigbrain',
      });
      return;
    }

    if (event === 'chat.done') {
      // Streamed reply complete: finalize the streaming bubble; the text
      // must NOT be re-added as a new message (it was already shown live).
      this.callbacks.onRunEnd?.();
      return;
    }

    if (event === 'chat.message') {
      // A terminal reply can be empty after a provider error. End the wait
      // before the transcript callback intentionally filters empty messages.
      this.callbacks.onRunEnd?.();
      const role = payload.role === 'system' ? 'system' : 'assistant';
      this.callbacks.onMessage?.({
        text: payload.text || '',
        role,
        timestamp: String(frame.timestamp || Date.now()),
        source: frame.source || 'bigbrain',
      });
      return;
    }

    if (event === 'brain.status') {
      this.callbacks.onAgentActivity?.({
        type: 'brain_status',
        name: payload.brain,
        detail: payload,
      });
      return;
    }

    const taskEvents = [
      'task.received', 'task.complete', 'task.failed', 'task.cancelled',
      'subtask.started', 'subtask.complete', 'subtask.failed',
      'brain.started', 'brain.complete',
      'task.progress',
    ];
    if (event && taskEvents.includes(event)) {
      // A session-wide user Stop also owns the pending front reply. A worker's
      // individual cancellation must not close an unrelated conversation turn.
      if (event === 'task.cancelled' && payload.session_id === this.sessionKey &&
          payload.mode === 'user' && !payload.task_id) this.callbacks.onRunEnd?.();
      this.callbacks.onAgentActivity?.({ type: event, detail: payload });
      // Worker completion does not end an unrelated front-brain reply.
      return;
    }

    if (event === 'system.status') {
      this.callbacks.onUserInfo?.({
        id: 'bigbrain',
        name: 'BigBrain',
        role: 'system',
      });
      return;
    }
    // Unknown events: forward as generic activity so nothing is silently lost.
    if (event) {
      this.callbacks.onAgentActivity?.({ type: event, detail: payload });
    }
  }

  private get _historyWanted(): boolean {
    // App registers callbacks before connect(); requesting history on
    // welcome is only useful if someone listens for catch-up or will call
    // loadHistory later — cheap either way (server keeps 200 max).
    return true;
  }

  private _emitStatus(messageId: string, status: string): void {
    this.callbacks.onMessageStatus?.(messageId, status);
  }

  private _updateStatus(status: string): void {
    this.callbacks.onStatusChange?.(status);
  }

  private _startKeepalive(): void {
    this._stopKeepalive();
    this.pongReceived = true;
    this.keepaliveTimer = setInterval(() => {
      if (!this.pongReceived) {
        this._onClose(); // treat as lost connection → reconnect
        return;
      }
      this.pongReceived = false;
      try {
        this.ws?.send(JSON.stringify({ type: 'ping' }));
      } catch (e) { /* onclose follows */ }
    }, KEEPALIVE_MS);
  }

  private _stopKeepalive(): void {
    if (this.keepaliveTimer) {
      clearInterval(this.keepaliveTimer);
      this.keepaliveTimer = null;
    }
  }

  private _onClose(): void {
    const wasConnected = this.connected;
    this.connected = false;
    this._stopKeepalive();
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this._updateStatus('disconnected');
      return;
    }
    this._updateStatus('connecting');
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 15_000);
    this.reconnectAttempts += 1;
    setTimeout(() => {
      this.connect();
      if (wasConnected) {
        setTimeout(() => this.callbacks.onReconnected?.(), 500);
      }
    }, delay);
  }
}
