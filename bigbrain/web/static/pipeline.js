/**
 * pipeline.js — Data Pipeline Runners (Decision D5)
 *
 * Agent defines pipelines: source + transform + component.
 * System manages lifecycle. No eval, no code injection.
 *
 * Source types:
 *   - bus: Internal MessageBus events
 *   - http-poll: Periodic HTTP GET with interval
 *   - websocket: Real-time WebSocket stream
 *
 * Transform: JSON path field mapping (no arbitrary code).
 */

// ============================================================
// PIPELINE BASE
// ============================================================

class Pipeline {
  /**
   * @param {string} id - Unique pipeline identifier
   * @param {object} definition - Pipeline definition from agent
   * @param {object} definition.source - { type, url, interval, filter }
   * @param {object} definition.transform - { fields: { outputKey: 'input.path.key' } }
   * @param {function} onData - Callback when transformed data is ready
   */
  constructor(id, definition, onData) {
    this.id = id;
    this.definition = definition;
    this.onData = onData;
    this._active = false;
    this._cleanup = null;
  }

  start() {
    if (this._active) return;
    this._active = true;
  }

  stop() {
    this._active = false;
    if (this._cleanup) {
      this._cleanup();
      this._cleanup = null;
    }
  }

  /**
   * Apply field mapping transform to raw data.
   *
   * @param {object} raw - Raw data from source
   * @returns {object} Transformed data
   */
  transform(raw) {
    const mapping = this.definition.transform?.fields;
    if (!mapping) return raw;

    const result = {};
    for (const [outKey, path] of Object.entries(mapping)) {
      result[outKey] = getNestedValue(raw, path);
    }
    return result;
  }
}

// ============================================================
// BUS PIPELINE — subscribes to MessageBus events
// ============================================================

class BusPipeline extends Pipeline {
  /**
   * @param {string} id
   * @param {object} def - Pipeline definition
   * @param {function} onData
   * @param {BusClient} busClient
   */
  constructor(id, def, onData, busClient) {
    super(id, def, onData);
    this._busClient = busClient;
    this._handler = null;
  }

  start() {
    super.start();
    const filter = this.definition.source.filter || {};

    this._handler = (msg) => {
      if (!this._active) return;
      const transformed = this.transform(msg.payload || msg);
      this.onData(transformed);
    };

    this._busClient.on(filter, this._handler);

    this._cleanup = () => {
      if (this._handler) {
        this._busClient.off(filter, this._handler);
        this._handler = null;
      }
    };
  }
}

// ============================================================
// HTTP-POLL PIPELINE — periodic API polling
// ============================================================

class HttpPollPipeline extends Pipeline {
  constructor(id, def, onData) {
    super(id, def, onData);
    this._timer = null;
  }

  start() {
    super.start();

    const url = this.definition.source.url;
    const interval = Math.max(
      this.definition.source.interval || 30000,
      5000 // Min 5s interval (constraint from architecture)
    );
    const headers = this.definition.source.headers || {};

    const poll = async () => {
      if (!this._active) return;
      try {
        const resp = await fetch(url, { headers });
        if (!resp.ok) {
          console.warn(`Pipeline ${this.id}: HTTP ${resp.status}`);
          return;
        }
        const raw = await resp.json();
        const transformed = this.transform(raw);
        this.onData(transformed);
      } catch (e) {
        console.warn(`Pipeline ${this.id}: fetch error:`, e.message);
      }
    };

    // Initial fetch
    poll();
    this._timer = setInterval(poll, interval);

    this._cleanup = () => {
      if (this._timer) {
        clearInterval(this._timer);
        this._timer = null;
      }
    };
  }
}

// ============================================================
// WEBSOCKET PIPELINE — real-time streaming
// ============================================================

class WebSocketPipeline extends Pipeline {
  constructor(id, def, onData) {
    super(id, def, onData);
    this._ws = null;
  }

  start() {
    super.start();

    const url = this.definition.source.url;

    try {
      this._ws = new WebSocket(url);
    } catch (e) {
      console.error(`Pipeline ${this.id}: WS connection failed:`, e);
      return;
    }

    this._ws.onmessage = (event) => {
      if (!this._active) return;
      try {
        const raw = JSON.parse(event.data);
        const transformed = this.transform(raw);
        this.onData(transformed);
      } catch (e) {
        // Might be text data
        this.onData(event.data);
      }
    };

    this._ws.onerror = (e) => {
      console.warn(`Pipeline ${this.id}: WS error`, e);
    };

    this._ws.onclose = () => {
      // Don't auto-reconnect; pipeline manager handles lifecycle
      console.log(`Pipeline ${this.id}: WS closed`);
    };

    this._cleanup = () => {
      if (this._ws) {
        this._ws.close(1000);
        this._ws = null;
      }
    };
  }
}

// ============================================================
// PIPELINE MANAGER
// ============================================================

/**
 * Manages pipeline lifecycle.
 * Enforces constraints: max 6 per workspace, min 5s poll, URL validation.
 */
class PipelineManager {
  /**
   * @param {BusClient} busClient - WebSocket bus client
   * @param {number} [maxPipelines=6] - Max concurrent pipelines
   */
  constructor(busClient, maxPipelines = 6) {
    this._busClient = busClient;
    this._pipelines = new Map();
    this.maxPipelines = maxPipelines;
  }

  /**
   * Create and start a pipeline.
   *
   * @param {string} id - Pipeline ID
   * @param {object} definition - Pipeline definition
   * @param {function} onData - Data callback
   * @returns {Pipeline|null} Created pipeline, or null if rejected
   */
  create(id, definition, onData) {
    // Enforce max pipelines
    if (this._pipelines.size >= this.maxPipelines) {
      console.warn(`PipelineManager: max ${this.maxPipelines} pipelines reached`);
      return null;
    }

    // Validate
    if (!definition.source?.type) {
      console.warn('PipelineManager: missing source.type');
      return null;
    }

    // URL validation for http/ws sources
    if (definition.source.url) {
      try {
        const url = new URL(definition.source.url);
        const allowed = ['http:', 'https:', 'ws:', 'wss:'];
        if (!allowed.includes(url.protocol)) {
          console.warn(`PipelineManager: blocked protocol ${url.protocol}`);
          return null;
        }
      } catch {
        console.warn('PipelineManager: invalid URL');
        return null;
      }
    }

    // Create appropriate pipeline type
    let pipeline;
    switch (definition.source.type) {
      case 'bus':
        pipeline = new BusPipeline(id, definition, onData, this._busClient);
        break;
      case 'http-poll':
        pipeline = new HttpPollPipeline(id, definition, onData);
        break;
      case 'websocket':
        pipeline = new WebSocketPipeline(id, definition, onData);
        break;
      default:
        console.warn(`PipelineManager: unknown source type "${definition.source.type}"`);
        return null;
    }

    this._pipelines.set(id, pipeline);
    pipeline.start();
    return pipeline;
  }

  /**
   * Stop and remove a pipeline.
   *
   * @param {string} id - Pipeline ID
   */
  destroy(id) {
    const pipeline = this._pipelines.get(id);
    if (pipeline) {
      pipeline.stop();
      this._pipelines.delete(id);
    }
  }

  /**
   * Stop all pipelines (workspace switch cleanup).
   */
  destroyAll() {
    for (const [id, pipeline] of this._pipelines) {
      pipeline.stop();
    }
    this._pipelines.clear();
  }

  /**
   * Get list of active pipeline IDs.
   *
   * @returns {string[]}
   */
  list() {
    return Array.from(this._pipelines.keys());
  }

  /**
   * Get a pipeline by ID.
   *
   * @param {string} id
   * @returns {Pipeline|undefined}
   */
  get(id) {
    return this._pipelines.get(id);
  }
}

// ============================================================
// UTILITY — nested value getter (JSON path notation)
// ============================================================

/**
 * Get a nested value from an object using dot notation.
 * e.g., getNestedValue({a: {b: {c: 42}}}, 'a.b.c') => 42
 *
 * @param {object} obj - Source object
 * @param {string} path - Dot-separated path (e.g., 'weather.temp.current')
 * @returns {*} Value at path, or undefined
 */
function getNestedValue(obj, path) {
  if (!path || !obj) return obj;

  const parts = path.split('.');
  let current = obj;

  for (const part of parts) {
    if (current === null || current === undefined) return undefined;

    // Handle array index: 'items.0.name'
    if (Array.isArray(current) && /^\d+$/.test(part)) {
      current = current[parseInt(part, 10)];
    } else {
      current = current[part];
    }
  }

  return current;
}

// ============================================================
// EXPORTS
// ============================================================

export {
  Pipeline,
  BusPipeline,
  HttpPollPipeline,
  WebSocketPipeline,
  PipelineManager,
  getNestedValue,
};
