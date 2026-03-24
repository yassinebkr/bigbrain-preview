/**
 * bus-client.js — WebSocket MessageBus Client
 *
 * Connects to the BigBrain web server via WebSocket.
 * Bridges browser panels to the Python MessageBus.
 * Auto-reconnects on disconnect.
 */

class BusClient {
  /**
   * @param {string} url - WebSocket URL (e.g., ws://localhost:8080/ws)
   * @param {object} [opts]
   * @param {number} [opts.reconnectMs=3000] - Reconnect interval
   * @param {number} [opts.maxReconnects=20] - Max reconnect attempts
   * @param {string} [opts.token] - Auth token (appended as ?token= for Basic Auth bypass)
   */
  constructor(url, opts = {}) {
    this.url = url;
    if (opts.token) {
      const sep = url.includes('?') ? '&' : '?';
      this.url = `${url}${sep}token=${encodeURIComponent(opts.token)}`;
    }
    this.reconnectMs = opts.reconnectMs || 3000;
    this.maxReconnects = opts.maxReconnects || 20;

    this._ws = null;
    this._handlers = [];   // { filter, handler }
    this._reconnects = 0;
    this._reconnectTimer = null;
    this._connected = false;
    this._queue = [];       // Messages queued while disconnected

    // Event callbacks
    this.onConnect = null;
    this.onDisconnect = null;
    this.onError = null;
  }

  /**
   * Connect to the WebSocket server.
   */
  connect() {
    if (this._ws && (this._ws.readyState === WebSocket.OPEN ||
                     this._ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      this._ws = new WebSocket(this.url);
    } catch (e) {
      console.error('BusClient: WebSocket creation failed:', e);
      this._scheduleReconnect();
      return;
    }

    this._ws.onopen = () => {
      this._connected = true;
      this._reconnects = 0;
      console.log('BusClient: connected');

      // Flush queued messages
      while (this._queue.length > 0) {
        const msg = this._queue.shift();
        this._ws.send(JSON.stringify(msg));
      }

      if (this.onConnect) this.onConnect();
    };

    this._ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        // Debug: log non-state messages
        if (msg.type !== 'state') {
          console.log(`[BUS] ${msg.type} ${msg.payload?.event || ''} src=${msg.source} handlers=${this._handlers.length}`);
        }
        this._dispatch(msg);
      } catch (e) {
        console.warn('BusClient: invalid message:', e);
      }
    };

    this._ws.onclose = (event) => {
      this._connected = false;
      console.log(`BusClient: disconnected (code=${event.code})`);
      if (this.onDisconnect) this.onDisconnect(event);
      this._scheduleReconnect();
    };

    this._ws.onerror = (event) => {
      console.error('BusClient: error', event);
      if (this.onError) this.onError(event);
    };
  }

  /**
   * Disconnect from the server.
   */
  disconnect() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this._reconnects = this.maxReconnects; // Prevent auto-reconnect

    if (this._ws) {
      this._ws.close(1000, 'Client disconnect');
      this._ws = null;
    }
    this._connected = false;
  }

  /**
   * Send a message to the server (which forwards to the Python bus).
   *
   * @param {object} msg - Message object
   */
  send(msg) {
    if (this._connected && this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(msg));
    } else {
      this._queue.push(msg);
    }
  }

  /**
   * Subscribe to bus messages matching a filter.
   *
   * @param {object} filter - Match criteria:
   *   { type: 'event', source: 'python_brain', event: 'brain.complete' }
   *   Empty filter {} matches all messages.
   *   Filter values can be strings (exact or prefix match).
   * @param {function} handler - Function called with matching messages
   */
  on(filter, handler) {
    this._handlers.push({ filter: filter || {}, handler });
  }

  /**
   * Remove a subscription.
   *
   * @param {object} filter - Same filter used in on()
   * @param {function} handler - Same handler function
   */
  off(filter, handler) {
    this._handlers = this._handlers.filter(
      (h) => h.handler !== handler || JSON.stringify(h.filter) !== JSON.stringify(filter)
    );
  }

  /**
   * Check if currently connected.
   *
   * @returns {boolean}
   */
  get connected() {
    return this._connected;
  }

  // ---- Internal ----

  _dispatch(msg) {
    for (const { filter, handler } of this._handlers) {
      if (this._matches(msg, filter)) {
        try {
          handler(msg);
        } catch (e) {
          console.error('BusClient: handler error:', e);
        }
      }
    }
  }

  _matches(msg, filter) {
    for (const [key, value] of Object.entries(filter)) {
      if (!value) continue;

      let msgValue;
      if (key === 'event') {
        // Special: match against payload.event
        msgValue = msg.payload?.event || '';
      } else {
        msgValue = msg[key];
      }

      if (typeof msgValue !== 'string') continue;

      // Prefix match: filter 'brain.' matches 'brain.started', 'brain.complete', etc.
      if (value.endsWith('.')) {
        if (!msgValue.startsWith(value)) return false;
      } else {
        if (msgValue !== value) return false;
      }
    }
    return true;
  }

  _scheduleReconnect() {
    if (this._reconnects >= this.maxReconnects) {
      console.warn('BusClient: max reconnects reached');
      return;
    }

    if (this._reconnectTimer) return;

    this._reconnects++;
    const delay = Math.min(
      this.reconnectMs * Math.pow(1.5, this._reconnects - 1),
      30000
    );

    console.log(`BusClient: reconnecting in ${Math.round(delay)}ms (attempt ${this._reconnects})`);
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connect();
    }, delay);
  }
}

export { BusClient };
