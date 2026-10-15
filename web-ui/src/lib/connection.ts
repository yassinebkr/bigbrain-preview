// OpenClaw Gateway WebSocket Connection — matches scratchy-v0 protocol exactly

// ── Cookie helpers (same as scratchy-v0) ──
function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

function getAuthToken(): string | null {
  // Priority: scratchy_session cookie → scratchy_auth cookie → localStorage aplot_auth_token
  return getCookie('scratchy_session') || getCookie('scratchy_auth') || localStorage.getItem('aplot_auth_token') || null;
}

// ── Types ──
interface ConnectionCallbacks {
  onMessage?: (message: { text: string; role: string; timestamp: string; source: string }) => void;
  onStreamDelta?: (message: { text: string; role: string; source: string }) => void;
  onStatusChange?: (status: string) => void;
  onAgentActivity?: (activity: { type: string; phase?: string; name?: string; detail?: any }) => void;
  onQueueDrained?: () => void;
  onQueueReplay?: (msg: { text: string; id: string; ts: number }) => void;
  onSendError?: (error: { message: string }, messageId?: string) => void;
  onMessageStatus?: (messageId: string, status: string) => void;
  onCanvasUpdate?: (payload: any) => void;
  onUserInfo?: (user: any) => void;
  onReconnected?: () => void;
  onRemoteUserMessage?: (message: any) => void;
  onResumeCatchUp?: (messages: any[]) => void;
  onRunEnd?: () => void;
}

// ── Connection ──
export class Connection {
  private ws: WebSocket | null = null;
  private callbacks: ConnectionCallbacks = {};
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 20;
  private messageIdCounter = 0;
  private pendingRequests: Record<string, (frame: any) => void> = {};
  private connected = false;
  private handshakeComplete = false;

  // Session
  sessionKey = 'agent:main:main';

  // Client ID for session continuity
  private _clientId: string;
  private _lastSeq = 0;
  private _resumed = false;

  // Run tracking (for lifecycle synthesis)
  private _runActive = false;
  private _currentRunId: string | null = null;
  private _runStartTimer: ReturnType<typeof setTimeout> | null = null;
  private _runEndTimer: ReturnType<typeof setTimeout> | null = null;
  private _showedToolIdle = false;
  private _pongReceived = true;
  private _keepaliveTimer: ReturnType<typeof setInterval> | null = null;
  private _healthCheckTimer: ReturnType<typeof setTimeout> | null = null;
  private _drainCallback: (() => void) | null = null;

  // Offline queue
  private _offlineQueue: Array<{ text: string; attachments: any[] | null; ts: number; id: string; retries: number }> = [];
  private readonly _OFFLINE_QUEUE_MAX_AGE = 4 * 60 * 60 * 1000;
  private readonly _MAX_RETRIES = 3;
  private _msgIdCounter = 0;

  // Event bindings (one-time)
  private _visibilityBound = false;
  private _onlineBound = false;

  // URL
  private url: string;

  constructor(config?: { gatewayUrl?: string; sessionKey?: string }) {
    this.url = config?.gatewayUrl || this._resolveGatewayUrl();
    if (config?.sessionKey) this.sessionKey = config.sessionKey;

    // Load client ID
    this._clientId = this._loadOrCreateClientId();
    this._lastSeq = parseInt(sessionStorage.getItem('scratchy_lastSeq') || '0', 10);
    this._offlineQueue = this._loadOfflineQueue();
  }

  // ── Callbacks ──
  on<K extends keyof ConnectionCallbacks>(event: K, callback: ConnectionCallbacks[K]): void {
    (this.callbacks as any)[event] = callback;
  }

  // ── Gateway URL resolution ──
  private _resolveGatewayUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws`;
  }

  // ── Client ID ──
  private _loadOrCreateClientId(): string {
    let id = sessionStorage.getItem('scratchy_clientId');
    if (!id) {
      id = 'sc-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem('scratchy_clientId', id);
    }
    return id;
  }

  private _persistLastSeq(): void {
    try { sessionStorage.setItem('scratchy_lastSeq', String(this._lastSeq)); } catch (e) {}
  }

  // ── Offline Queue ──
  private _storageKey(): string {
    return 'scratchy_offline_queue:' + this.sessionKey;
  }

  private _loadOfflineQueue(): Array<{ text: string; attachments: any[] | null; ts: number; id: string; retries: number }> {
    try {
      const raw = localStorage.getItem(this._storageKey());
      if (!raw) return [];
      const queue = JSON.parse(raw);
      if (!Array.isArray(queue)) return [];
      const now = Date.now();
      return queue.filter((msg: any) => msg.ts && (now - msg.ts) < this._OFFLINE_QUEUE_MAX_AGE);
    } catch (e) {
      return [];
    }
  }

  private _persistOfflineQueue(): void {
    try { localStorage.setItem(this._storageKey(), JSON.stringify(this._offlineQueue)); } catch (e) {}
  }

  private _generateMessageId(): string {
    this._msgIdCounter++;
    return 'msg-' + Date.now() + '-' + this._msgIdCounter;
  }

  private _emitStatus(messageId: string, status: string): void {
    this.callbacks.onMessageStatus?.(messageId, status);
  }

  // ── Connect ──
  connect(): void {
    if (this.ws) {
      try { this.ws.close(); } catch (e) {}
      this.ws = null;
    }
    this.connected = false;
    this.handshakeComplete = false;
    this._resumed = false;
    this._updateStatus('connecting');

    // Build URL with clientId + lastSeq
    let wsUrl = this.url;
    const sep = wsUrl.includes('?') ? '&' : '?';
    wsUrl += sep + 'clientId=' + encodeURIComponent(this._clientId) + '&lastSeq=' + this._lastSeq;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => this._sendHandshake();
    this.ws.onmessage = (event) => this._onMessage(event);
    this.ws.onerror = () => {/* handled by onclose */};
    this.ws.onclose = () => {
      this.connected = false;
      this.handshakeComplete = false;
      this._stopClientKeepalive();
      this.pendingRequests = {};
      this._updateStatus('disconnected');
      this._tryReconnect();
    };

    // Visibility change
    if (!this._visibilityBound) {
      this._visibilityBound = true;
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && (!this.ws || this.ws.readyState !== WebSocket.OPEN)) {
          this.reconnectAttempts = 0;
          this._tryReconnect();
        }
      });
    }

    // Network online
    if (!this._onlineBound) {
      this._onlineBound = true;
      window.addEventListener('online', () => {
        this.reconnectAttempts = 0;
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) this._tryReconnect();
      });
    }
  }

  // ── Handshake ──
  private _sendHandshake(): void {
    const token = getAuthToken();
    const connectFrame = {
      type: 'req',
      id: this._nextId(),
      method: 'connect',
      params: {
        minProtocol: 3,
        maxProtocol: 3,
        client: {
          id: 'webchat',
          displayName: 'Aplot AI',
          version: '3.0.0',
          platform: 'web',
          mode: 'webchat',
        },
        caps: ['tool-events'],
        role: 'operator',
        ...(token ? { auth: { token } } : {}),
      },
    };
    this.ws?.send(JSON.stringify(connectFrame));
  }

  // ── Message handler ──
  private _onMessage(event: MessageEvent): void {
    let frame: any;
    try {
      frame = JSON.parse(event.data);
    } catch {
      return;
    }
    try {
      this._handleFrame(frame);
    } catch (e) {
      console.error('[Connection] Frame handling error:', e);
    }
  }

  private _handleFrame(frame: any): void {
    // Pong
    if (frame.type === 'pong') {
      this._pongReceived = true;
      return;
    }

    // User info
    if (frame.type === 'user-info' && frame.user) {
      this.callbacks.onUserInfo?.(frame.user);
      return;
    }

    // Compaction
    if (frame.type === 'compaction') {
      if (this._runStartTimer) { clearTimeout(this._runStartTimer); this._runStartTimer = null; }
      if (this._runEndTimer) { clearTimeout(this._runEndTimer); this._runEndTimer = null; }
      this.callbacks.onAgentActivity?.({ type: 'compaction', phase: frame.phase || 'start', detail: frame });
      return;
    }

    // Replay protocol
    if (frame.type === 'replay_start') {
      return;
    }
    if (frame.type === 'replay_end') {
      this._persistLastSeq();
      return;
    }

    // Seq envelope unwrap
    if (typeof frame.seq === 'number' && frame.frame) {
      this._lastSeq = frame.seq;
      this._persistLastSeq();
      frame = frame.frame;
    }

    // Response
    if (frame.type === 'res') {
      // Connect response
      if (!this.handshakeComplete) {
        if (frame.ok) {
          this._resumed = !!frame.payload?.resumed;
          this.handshakeComplete = true;
          this.connected = true;
          this.reconnectAttempts = 0;
          this._updateStatus('connected');
          this._startClientKeepalive();
          const wasReconnect = this.reconnectAttempts > 0;
          const wasResumed = this._resumed;
          this._drainCallback = () => {
            this._drainCallback = null;
            if (wasReconnect && !wasResumed) {
              setTimeout(() => this.callbacks.onReconnected?.(), 500);
            }
          };
          this._drainOfflineQueue();
        } else {
          this.ws?.close();
        }
        // Route to pending request
        if (this.pendingRequests[frame.id]) {
          this.pendingRequests[frame.id](frame);
          delete this.pendingRequests[frame.id];
        }
        return;
      }

      // Route responses
      if (this.pendingRequests[frame.id]) {
        this.pendingRequests[frame.id](frame);
        delete this.pendingRequests[frame.id];
      }
      return;
    }

    // Events
    if (frame.type === 'event') {
      this._handleEvent(frame);
      return;
    }
  }

  // ── Event handler ──
  private _handleEvent(frame: any): void {
    // Canvas update
    if (frame.event === 'canvas-update' && frame.payload) {
      this.callbacks.onCanvasUpdate?.(frame.payload);
      return;
    }

    // Filter by session
    if (frame.payload?.sessionKey && frame.payload.sessionKey !== this.sessionKey) return;

    // Agent events (streaming deltas)
    if (frame.event === 'agent' && frame.payload) {
      const stream = frame.payload.stream;
      const data = frame.payload.data || {};
      const runId = frame.payload.runId;

      if (runId && runId !== this._currentRunId) {
        this._currentRunId = runId;
        this._runActive = true;
        this._showedToolIdle = false;
        this.callbacks.onAgentActivity?.({ type: 'thinking', phase: 'start' });

        // 15s timeout fallback
        if (this._runStartTimer) clearTimeout(this._runStartTimer);
        this._runStartTimer = setTimeout(() => {
          if (this._runActive && this._currentRunId === runId) this._endRun();
        }, 15000);
      }

      if (stream === 'tool' && data.phase === 'start' && data.name) {
        if (this._runStartTimer) { clearTimeout(this._runStartTimer); this._runStartTimer = null; }
        this.callbacks.onAgentActivity?.({ type: 'tool', name: data.name, phase: 'start', detail: data });
      } else if (stream === 'tool' && (data.phase === 'end' || data.phase === 'error')) {
        this.callbacks.onAgentActivity?.({ type: 'tool', name: data.name || '', phase: 'end', detail: data });
      } else if (stream === 'compaction') {
        if (this._runStartTimer) { clearTimeout(this._runStartTimer); this._runStartTimer = null; }
        if (this._runEndTimer) { clearTimeout(this._runEndTimer); this._runEndTimer = null; }
        this.callbacks.onAgentActivity?.({ type: 'compaction', phase: data.phase || 'start', detail: data });
      } else if (stream === 'assistant' && data.delta) {
        if (this._runStartTimer) { clearTimeout(this._runStartTimer); this._runStartTimer = null; }
        if (this._showedToolIdle) {
          this.callbacks.onAgentActivity?.({ type: 'done', phase: 'end' });
          this._showedToolIdle = false;
        }
        if (this._runEndTimer) clearTimeout(this._runEndTimer);
        this._runEndTimer = setTimeout(() => {
          if (this._runActive) this._endRun();
        }, 5000);
      }
      return;
    }

    // Chat events
    if (frame.event === 'chat' && frame.payload) {
      // Final message - don't call onMessage, just end the run
      // The streaming text will be finalized by onRunEnd
      if (frame.payload.state === 'final' && frame.payload.message) {
        this._endRun();
      }

      // Delta (streaming)
      if (frame.payload.state === 'delta' && frame.payload.message) {
        const msg = frame.payload.message;
        let text = '';
        if (msg.content && Array.isArray(msg.content)) {
          text = msg.content.filter((b: any) => b.type === 'text' && b.text).map((b: any) => b.text).join('\n');
        }
        if (text && !this._isSystemNoise(text) && this.callbacks.onStreamDelta) {
          this.callbacks.onStreamDelta({ text, role: 'assistant', source: 'stream' });
        }
      }

      // Error
      if (frame.payload.state === 'error' && frame.payload.errorMessage) {
        this.callbacks.onMessage?.({
          text: '⚠️ ' + frame.payload.errorMessage,
          role: 'assistant',
          timestamp: new Date().toISOString(),
          source: 'stream',
        });
        this._endRun();
      }
    }
  }

  // ── Send message ──
  send(text: string, attachments?: any[]): string {
    const messageId = this._generateMessageId();

    if (!this.connected || !this.handshakeComplete) {
      this._offlineQueue.push({ text, attachments: attachments || null, ts: Date.now(), id: messageId, retries: 0 });
      this._persistOfflineQueue();
      this._emitStatus(messageId, 'queued');
      this.callbacks.onStatusChange?.('disconnected');
      return messageId;
    }

    this._emitStatus(messageId, 'sending');

    // Attachments → HTTP upload
    if (attachments && attachments.length > 0) {
      this._sendViaHttp(text, attachments, messageId, 0);
      return messageId;
    }

    // Plain text → WebSocket
    const reqId = this._nextId();
    const frame = {
      type: 'req',
      id: reqId,
      method: 'chat.send',
      params: {
        sessionKey: this.sessionKey,
        message: text,
        idempotencyKey: this._nextId(),
      },
    };

    this.pendingRequests[reqId] = (response: any) => {
      if (!response.ok) {
        this._emitStatus(messageId, 'failed');
        this.callbacks.onSendError?.({ message: response.error || 'Send failed' }, messageId);
      } else {
        this._emitStatus(messageId, 'sent');
      }
    };

    this.ws?.send(JSON.stringify(frame));
    return messageId;
  }

  // ── HTTP file upload ──
  private _sendViaHttp(text: string, attachments: any[], messageId: string, retryCount: number): void {
    const formData = new FormData();
    formData.append('message', text || '');
    formData.append('sessionKey', this.sessionKey);

    for (let i = 0; i < attachments.length; i++) {
      const att = attachments[i];
      if (att.file) {
        formData.append(att.type?.startsWith('image/') ? 'image' : 'file', att.file, att.name);
      }
    }

    fetch('/api/send', { method: 'POST', body: formData, credentials: 'same-origin' })
      .then((res) => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then((data: any) => {
        if (data.ok) {
          this._emitStatus(messageId, 'sent');
        } else {
          throw new Error(data.error || 'Server error');
        }
      })
      .catch((err) => {
        this._requeueFailedHttp(text, attachments, messageId, retryCount, err);
      });
  }

  private _requeueFailedHttp(text: string, attachments: any[], messageId: string, retryCount: number, err: Error): void {
    const nextRetry = retryCount + 1;
    if (nextRetry > this._MAX_RETRIES) {
      this._emitStatus(messageId, 'failed');
      this.callbacks.onSendError?.({ message: 'Upload failed after ' + this._MAX_RETRIES + ' retries: ' + err.message }, messageId);
      return;
    }
    this._offlineQueue.push({ text, attachments, ts: Date.now(), id: messageId || this._generateMessageId(), retries: nextRetry });
    this._persistOfflineQueue();
    this._emitStatus(messageId, 'queued');
  }

  // ── History ──
  loadHistory(callback?: (frame: any) => void): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN || !this.handshakeComplete) {
      callback?.({ ok: false, error: { message: 'not connected' } });
      return;
    }
    const id = this._nextId();
    this.pendingRequests[id] = callback || (() => {});
    this.ws.send(JSON.stringify({
      type: 'req', id, method: 'chat.history',
      params: { sessionKey: this.sessionKey, limit: 50 },
    }));
  }

  // ── Session switch ──
  switchSession(newSessionKey: string): void {
    if (!/^[a-zA-Z0-9:._-]+$/.test(newSessionKey)) return;
    this._persistOfflineQueue();
    this.sessionKey = newSessionKey;
    this._offlineQueue = this._loadOfflineQueue();
    this.disconnect();
    this.reconnectAttempts = 0;
    this.connect();
  }

  // ── Disconnect ──
  disconnect(): void {
    this.reconnectAttempts = this.maxReconnectAttempts;
    this._stopClientKeepalive();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
    this.handshakeComplete = false;
    this._updateStatus('disconnected');
  }

  // ── Force reconnect ──
  forceReconnect(): void {
    this.connected = false;
    this.handshakeComplete = false;
    this.reconnectAttempts = 1;
    this.pendingRequests = {};
    this._runActive = false;
    this._currentRunId = null;
    if (this._runStartTimer) { clearTimeout(this._runStartTimer); this._runStartTimer = null; }
    if (this._runEndTimer) clearTimeout(this._runEndTimer);
    if (this.ws) { try { this.ws.close(); } catch (e) {} this.ws = null; }
    this.connect();
  }

  // ── Health check ──
  checkHealth(callback: (alive: boolean) => void, timeoutMs = 3000): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) { callback(false); return; }
    const id = this._nextId();
    let timedOut = false;
    this._healthCheckTimer = setTimeout(() => {
      timedOut = true;
      delete this.pendingRequests[id];
      callback(false);
    }, timeoutMs);
    this.pendingRequests[id] = () => {
      if (timedOut) return;
      clearTimeout(this._healthCheckTimer!);
      this._healthCheckTimer = null;
      callback(true);
    };
    this.ws.send(JSON.stringify({ type: 'req', id, method: 'chat.history', params: { sessionKey: this.sessionKey, limit: 1 } }));
  }

  // ── Run lifecycle ──
  private _endRun(): void {
    if (!this._runActive) return;
    this._runActive = false;
    this._currentRunId = null;
    if (this._runStartTimer) { clearTimeout(this._runStartTimer); this._runStartTimer = null; }
    if (this._runEndTimer) clearTimeout(this._runEndTimer);
    this._showedToolIdle = false;
    this.callbacks.onAgentActivity?.({ type: 'done', phase: 'end' });
    this.callbacks.onRunEnd?.();
  }

  // ── System noise filter ──
  private _isSystemNoise(text: string): boolean {
    if (!text) return true;
    let t = text.trim().replace(/^\[SecurityPlugin Canary\][^\n]*\n?/, '').trim();
    if (!t) return true;
    if (/^A background task .+ just completed/m.test(t)) return true;
    if (/^Stats: runtime .+ sessionKey agent:/m.test(t)) return true;
    if (/Summarize this naturally for the user/m.test(t)) return true;
    if (/^System:\s*\[/m.test(t)) return true;
    if (/^GatewayRestart:/m.test(t)) return true;
    if (/^\[SecurityPlugin[ :L]/m.test(t)) return true;
    if (/\[securityplugin:source=/m.test(t)) return true;
    if (/(?:^|\s)NO_REPLY(?:\s|$)/.test(t)) return true;
    if (/(?:^|\s)HEARTBEAT_OK(?:\s|$)/.test(t)) return true;
    if (/^Read HEARTBEAT\.md/m.test(t)) return true;
    if (/^sessionKey agent:main:subagent:/m.test(t)) return true;
    return false;
  }

  // ── Offline queue drain ──
  private _drainOfflineQueue(): void {
    if (this._offlineQueue.length === 0) {
      this.callbacks.onQueueDrained?.();
      this._drainCallback?.();
      return;
    }
    const queue = this._offlineQueue.slice();
    this._offlineQueue = [];
    this._persistOfflineQueue();
    let i = 0;
    const sendNext = () => {
      if (i >= queue.length) {
        this.callbacks.onQueueDrained?.();
        this._drainCallback?.();
        return;
      }
      if (!this.connected || !this.handshakeComplete) {
        for (let j = i; j < queue.length; j++) this._offlineQueue.push(queue[j]);
        this._persistOfflineQueue();
        return;
      }
      const msg = queue[i++];
      this.callbacks.onQueueReplay?.({ text: msg.text, id: msg.id, ts: msg.ts });
      if (msg.retries > this._MAX_RETRIES) {
        this._emitStatus(msg.id, 'failed');
        this.callbacks.onSendError?.({ message: 'Max retries exceeded' }, msg.id);
        setTimeout(sendNext, 50);
        return;
      }
      this._emitStatus(msg.id, 'sending');
      if (msg.attachments && msg.attachments.length > 0) {
        this._sendViaHttp(msg.text, msg.attachments, msg.id, msg.retries || 0);
        setTimeout(sendNext, 300);
        return;
      }
      const reqId = this._nextId();
      this.ws?.send(JSON.stringify({
        type: 'req', id: reqId, method: 'chat.send',
        params: { sessionKey: this.sessionKey, message: msg.text, idempotencyKey: this._nextId() },
      }));
      setTimeout(sendNext, 300);
    };
    sendNext();
  }

  // ── Keepalive ──
  private _startClientKeepalive(): void {
    this._stopClientKeepalive();
    this._pongReceived = true;
    this._keepaliveTimer = setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      if (!this._pongReceived) { this.forceReconnect(); return; }
      this._pongReceived = false;
      try { this.ws.send(JSON.stringify({ type: 'ping', ts: Date.now() })); } catch (e) {}
    }, 25000);
  }

  private _stopClientKeepalive(): void {
    if (this._keepaliveTimer) { clearInterval(this._keepaliveTimer); this._keepaliveTimer = null; }
  }

  // ── Reconnect ──
  private _tryReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 15000);
    setTimeout(() => { if (!this.connected) this.connect(); }, delay);
  }

  // ── Status ──
  private _updateStatus(status: string): void {
    this.callbacks.onStatusChange?.(status);
  }

  private _nextId(): string {
    this.messageIdCounter++;
    return `scratchy-${Date.now()}-${this.messageIdCounter}`;
  }
}