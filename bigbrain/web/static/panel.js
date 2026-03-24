/**
 * panel.js — Autonomous Panel System
 *
 * Panels are self-contained bus subscribers (Decision D4).
 * Agent controls show/hide. Panels control their own content.
 *
 * Panel contract:
 *   mount(slotEl)       — Render into a slot element
 *   subscribe(busClient) — Start listening to bus events
 *   onEvent(event)      — Handle a bus event
 *   unmount()           — Cleanup
 *   getState()          — Return serializable state
 *   setState(state)     — Restore from saved state
 */

// ============================================================
// HELPERS
// ============================================================

/** Escape HTML to prevent XSS in user-facing text. */
function _escapeHtml(text) {
  const el = document.createElement('span');
  el.textContent = text;
  return el.innerHTML;
}

/** Format a compact timestamp for chat / bus messages. */
function _timestamp(fmt = 'HH:mm') {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return fmt === 'HH:mm:ss' ? `${hh}:${mm}:${ss}` : `${hh}:${mm}`;
}

// ============================================================
// BASE PANEL
// ============================================================

class BasePanel {
  /**
   * @param {string} id - Unique panel identifier
   * @param {object} config - Panel configuration
   * @param {string} config.title - Display title
   * @param {string} [config.icon] - Emoji icon
   * @param {string} [config.type] - Panel type name
   */
  constructor(id, config = {}) {
    this.id = id;
    this.title = config.title || id;
    this.icon = config.icon || '📦';
    this.type = config.type || 'base';
    this.el = null;
    this._busClient = null;
    this._subscriptions = [];
    this._mounted = false;
  }

  /**
   * Mount the panel into a container element.
   * Creates the panel DOM structure with title bar + content area.
   *
   * @param {HTMLElement} container - Container element (grid slot)
   * @returns {HTMLElement} The panel root element
   */
  mount(container) {
    if (this._mounted) return this.el;

    this.el = document.createElement('div');
    this.el.className = 'panel';
    this.el.dataset.panelId = this.id;
    this.el.dataset.panelType = this.type;

    // Title bar (always visible, even when collapsed)
    const titleBar = document.createElement('div');
    titleBar.className = 'panel-title-bar';
    titleBar.innerHTML = `
      <span class="panel-icon">${this.icon}</span>
      <span class="panel-title">${_escapeHtml(this.title)}</span>
      <span class="panel-actions">
        <button class="panel-btn panel-btn-collapse" title="Toggle collapse">▾</button>
      </span>
    `;

    // Click title bar → request collapse (let app.js orchestrate FLIP)
    titleBar.addEventListener('click', (e) => {
      if (e.target.closest('.panel-btn')) return;
      this._requestCollapseToggle();
    });

    // Collapse button
    titleBar.querySelector('.panel-btn-collapse')
      .addEventListener('click', () => this._requestCollapseToggle());

    // Content area
    const content = document.createElement('div');
    content.className = 'panel-content';

    this.el.appendChild(titleBar);
    this.el.appendChild(content);

    container.appendChild(this.el);
    this._mounted = true;

    // Let subclass render its content
    this.renderContent(content);

    return this.el;
  }

  /**
   * Override in subclass to render panel-specific content.
   *
   * @param {HTMLElement} contentEl - The .panel-content element
   */
  renderContent(contentEl) {
    contentEl.innerHTML = `
      <div class="panel-empty">
        <span class="panel-empty-icon">📦</span>
        <span class="panel-empty-text">Empty panel</span>
      </div>`;
  }

  /**
   * Subscribe to bus events.
   *
   * @param {BusClient} busClient - WebSocket bus client
   */
  subscribe(busClient) {
    this._busClient = busClient;
    this._setupSubscriptions();
  }

  /**
   * Override to set up bus subscriptions.
   * Use this._addSubscription(filter, handler).
   */
  _setupSubscriptions() {}

  /**
   * Register a bus subscription.
   *
   * @param {object} filter - Event filter { type, source, event }
   * @param {function} handler - Handler function
   */
  _addSubscription(filter, handler) {
    if (!this._busClient) return;
    const sub = { filter, handler: handler.bind(this) };
    this._subscriptions.push(sub);
    this._busClient.on(filter, sub.handler);
  }

  /**
   * Handle a bus event. Override in subclass.
   *
   * @param {object} event - Bus event data
   */
  onEvent(event) {}

  /**
   * Unmount and cleanup.
   */
  unmount() {
    for (const sub of this._subscriptions) {
      if (this._busClient) {
        this._busClient.off(sub.filter, sub.handler);
      }
    }
    this._subscriptions = [];
    this._busClient = null;

    if (this.el && this.el.parentNode) {
      this.el.remove();
    }
    this.el = null;
    this._mounted = false;
  }

  /**
   * Get serializable panel state for persistence.
   *
   * @returns {object} State object
   */
  getState() {
    return {
      id: this.id,
      type: this.type,
      title: this.title,
      collapsed: this.el ? this.el.classList.contains('panel-collapsed') : false,
    };
  }

  /**
   * Restore panel state.
   *
   * @param {object} state - Previously saved state
   */
  setState(state) {
    if (state.collapsed && this.el) {
      this.el.classList.add('panel-collapsed');
    }
  }

  /**
   * Get the content element.
   *
   * @returns {HTMLElement|null}
   */
  getContentEl() {
    return this.el ? this.el.querySelector('.panel-content') : null;
  }

  /**
   * Update the title bar text.
   *
   * @param {string} title
   */
  setTitle(title) {
    this.title = title;
    if (this.el) {
      const titleEl = this.el.querySelector('.panel-title');
      if (titleEl) titleEl.textContent = title;
    }
  }

  /**
   * Dispatch a bubbling event so app.js can orchestrate FLIP animation
   * and grid adaptation.  The actual class toggle happens in app.js.
   */
  _requestCollapseToggle() {
    if (!this.el) return;
    this.el.dispatchEvent(new CustomEvent('panel-collapse-toggle', {
      bubbles: true,
      detail: { panelId: this.id },
    }));
  }

  /**
   * Called by app.js AFTER the collapsed class has been toggled
   * to update visual affordances (button icon).
   */
  _onCollapseToggle() {
    const btn = this.el?.querySelector('.panel-btn-collapse');
    if (!btn) return;
    const collapsed = this.el.classList.contains('panel-collapsed');
    btn.textContent = collapsed ? '▸' : '▾';
  }
}

// ============================================================
// BUILT-IN PANELS
// ============================================================

/**
 * Chat panel — displays conversation messages.
 */
class ChatPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: 'Chat', icon: '💬', type: 'chat', ...config });
    this.messages = [];
  }

  renderContent(el) {
    el.innerHTML = `
      <div class="chat-messages" id="chat-${this.id}">
        <div class="panel-empty">
          <span class="panel-empty-icon">💬</span>
          <span class="panel-empty-text">Start a conversation with BigBrain</span>
          <span class="panel-empty-hint">Type a message below and press Enter</span>
        </div>
      </div>
    `;
  }

  _setupSubscriptions() {
    this._addSubscription(
      { type: 'event', event: 'chat.message' },
      (msg) => this.addMessage(msg.payload)
    );
  }

  addMessage(data) {
    const container = this.el?.querySelector('.chat-messages');
    if (!container) return;

    // Clear empty state on first message
    const empty = container.querySelector('.panel-empty');
    if (empty) empty.remove();

    const role = data.role || 'system';
    const text = data.text || data.content || '';
    const time = _timestamp('HH:mm');

    const msgEl = document.createElement('div');
    msgEl.className = `chat-msg chat-msg-${role}`;
    msgEl.innerHTML = `
      <div class="chat-msg-body">${_escapeHtml(text)}</div>
      <div class="chat-msg-timestamp">${time}</div>
    `;
    container.appendChild(msgEl);
    container.scrollTop = container.scrollHeight;

    this.messages.push({ role, text, timestamp: Date.now() });
  }
}

/**
 * Brain Status panel — shows status of all brains.
 */
class BrainStatusPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: 'Brains', icon: '🧠', type: 'brain-status', ...config });
    this.brains = new Map();
  }

  renderContent(el) {
    el.innerHTML = `<div class="brain-list">
      <div class="panel-empty">
        <span class="panel-empty-icon">🧠</span>
        <span class="panel-empty-text">Waiting for brain activity</span>
        <span class="panel-empty-hint">Brains will appear here when active</span>
      </div>
    </div>`;
  }

  _setupSubscriptions() {
    // Brain-specific events
    this._addSubscription(
      { type: 'event', event: 'brain.' },
      (msg) => this._handleBrainEvent(msg)
    );
    this._addSubscription(
      { type: 'state', event: 'brain.' },
      (msg) => this._handleBrainEvent(msg)
    );
    // Orchestrator subtask events (these carry brain names)
    this._addSubscription(
      { type: 'event', event: 'subtask.' },
      (msg) => this._handleBrainEvent(msg)
    );
    this._addSubscription(
      { type: 'event', event: 'task.' },
      (msg) => this._handleBrainEvent(msg)
    );
    // Brain progress messages use PROGRESS type
    this._addSubscription(
      { type: 'progress' },
      (msg) => this._handleBrainEvent(msg)
    );
    // Orchestrator events
    this._addSubscription(
      { type: 'event', event: 'orchestrator.' },
      (msg) => this._handleBrainEvent(msg)
    );
  }

  _handleBrainEvent(msg) {
    const event = msg.payload?.event || '';
    const brainName = msg.payload?.brain || msg.payload?.target_brain || msg.source;
    let status = 'idle';

    if (event.includes('started') || event.includes('received')) status = 'busy';
    else if (event.includes('complete')) status = 'idle';
    else if (event.includes('error') || event.includes('failed')) status = 'error';
    else if (event.includes('progress')) status = 'busy';

    this.brains.set(brainName, {
      status,
      task: msg.payload?.task_type || '',
      updated: Date.now(),
    });

    this._renderBrains();
  }

  _renderBrains() {
    const list = this.el?.querySelector('.brain-list');
    if (!list) return;

    list.innerHTML = '';
    for (const [name, info] of this.brains) {
      const statusLabel = { idle: 'Idle', busy: 'Working', error: 'Error' }[info.status] || 'Unknown';

      const item = document.createElement('div');
      item.className = `brain-item brain-${info.status}`;
      item.innerHTML = `
        <span class="brain-indicator"></span>
        <span class="brain-name">${_escapeHtml(name)}</span>
        ${info.task ? `<span class="brain-task">${_escapeHtml(info.task)}</span>` : ''}
        <span class="brain-status-badge">${statusLabel}</span>
      `;
      list.appendChild(item);
    }
  }
}

/**
 * Task List panel — shows active and completed tasks.
 */
class TaskListPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: 'Tasks', icon: '📋', type: 'task-list', ...config });
    this.tasks = new Map();
  }

  renderContent(el) {
    el.innerHTML = `<div class="task-list">
      <div class="panel-empty">
        <span class="panel-empty-icon">📋</span>
        <span class="panel-empty-text">No active tasks</span>
        <span class="panel-empty-hint">Send a message to start a task</span>
      </div>
    </div>`;
  }

  _setupSubscriptions() {
    this._addSubscription({ type: 'task' }, (msg) => {
      this.tasks.set(msg.id, {
        id: msg.id,
        type: msg.payload?.type || msg.payload?.task_type || 'unknown',
        target: msg.target,
        status: 'running',
        progress: 0,
        started: Date.now(),
      });
      this._renderTasks();
    });
    this._addSubscription({ type: 'result' }, (msg) => {
      const taskId = msg.reply_to;
      if (taskId && this.tasks.has(taskId)) {
        const task = this.tasks.get(taskId);
        task.status = msg.payload?.success ? 'complete' : 'failed';
        task.progress = 100;
        this._renderTasks();
      }
    });
    // Orchestrator events (task.received, subtask.started, etc.)
    this._addSubscription({ type: 'event', event: 'task.' }, (msg) => {
      const event = msg.payload?.event || '';
      const taskId = msg.payload?.task_id || msg.id;
      if (event.includes('received') || event.includes('started')) {
        this.tasks.set(taskId, {
          id: taskId,
          type: msg.payload?.task_type || event,
          target: msg.payload?.brain || msg.target,
          status: 'running',
          progress: 0,
          started: Date.now(),
        });
        this._renderTasks();
      } else if (event.includes('complete')) {
        if (this.tasks.has(taskId)) {
          this.tasks.get(taskId).status = 'complete';
          this.tasks.get(taskId).progress = 100;
          this._renderTasks();
        }
      } else if (event.includes('failed') || event.includes('cancelled')) {
        if (this.tasks.has(taskId)) {
          this.tasks.get(taskId).status = 'failed';
          this._renderTasks();
        }
      }
    });
    this._addSubscription({ type: 'event', event: 'subtask.' }, (msg) => {
      const event = msg.payload?.event || '';
      const taskId = msg.payload?.subtask_id || msg.id;
      if (event.includes('started')) {
        this.tasks.set(taskId, {
          id: taskId,
          type: msg.payload?.brain || 'subtask',
          target: msg.payload?.brain || msg.target,
          status: 'running',
          progress: 0,
          started: Date.now(),
        });
        this._renderTasks();
      } else if (event.includes('complete') || event.includes('failed')) {
        if (this.tasks.has(taskId)) {
          this.tasks.get(taskId).status = event.includes('complete') ? 'complete' : 'failed';
          this.tasks.get(taskId).progress = 100;
          this._renderTasks();
        }
      }
    });
    this._addSubscription(
      { type: 'progress' },
      (msg) => {
        const taskId = msg.reply_to || msg.payload?.task_id;
        if (taskId && this.tasks.has(taskId)) {
          const task = this.tasks.get(taskId);
          task.progress = msg.payload?.progress || task.progress;
          task.status = 'running';
          this._renderTasks();
        }
      }
    );
  }

  _renderTasks() {
    const list = this.el?.querySelector('.task-list');
    if (!list) return;

    list.innerHTML = '';
    for (const [, task] of this.tasks) {
      const icon = { running: '⏳', complete: '✅', failed: '❌' }[task.status] || '⏳';
      const statusLabel = { running: 'Running', complete: 'Done', failed: 'Failed' }[task.status] || 'Pending';

      const item = document.createElement('div');
      item.className = `task-item task-${task.status}`;
      item.innerHTML = `
        <div class="task-item-header">
          <span class="task-icon">${icon}</span>
          <span class="task-type">${_escapeHtml(task.type)}</span>
          <span class="task-status-badge">${statusLabel}</span>
        </div>
        <div style="padding-left:24px">
          <span class="task-target">${_escapeHtml(task.target || '')}</span>
        </div>
        <div class="task-progress-bar">
          <div class="task-progress-fill" style="width:${task.progress}%"></div>
        </div>
      `;
      list.appendChild(item);
    }
  }
}

/**
 * Bus Monitor panel — shows real-time message flow.
 */
class BusMonitorPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: 'Bus', icon: '📡', type: 'bus-monitor', ...config });
    this.maxMessages = 50;
  }

  renderContent(el) {
    el.innerHTML = `<div class="bus-messages">
      <div class="panel-empty">
        <span class="panel-empty-icon">📡</span>
        <span class="panel-empty-text">Listening for bus messages</span>
        <span class="panel-empty-hint">Messages will stream in real-time</span>
      </div>
    </div>`;
  }

  _setupSubscriptions() {
    // Subscribe to ALL messages
    this._addSubscription({}, (msg) => this._addMessage(msg));
  }

  _addMessage(msg) {
    const container = this.el?.querySelector('.bus-messages');
    if (!container) return;

    // Clear empty state
    const empty = container.querySelector('.panel-empty');
    if (empty) empty.remove();

    const type = msg.type?.toUpperCase?.() || msg.type || 'EVENT';
    const source = msg.source || '?';
    const target = msg.target || '*';
    const event = msg.payload?.event || msg.payload?.type || '';
    const time = _timestamp('HH:mm:ss');

    const msgEl = document.createElement('div');
    msgEl.className = `bus-msg bus-msg-${type.toLowerCase()}`;
    msgEl.innerHTML = `
      <span class="bus-type">${_escapeHtml(type)}</span>
      <span class="bus-route">${_escapeHtml(source)} → ${_escapeHtml(target)}</span>
      <span class="bus-event">${_escapeHtml(event)}</span>
      <span class="bus-time">${time}</span>
    `;

    container.appendChild(msgEl);

    // Prune old messages
    while (container.children.length > this.maxMessages) {
      container.removeChild(container.firstChild);
    }

    container.scrollTop = container.scrollHeight;
  }
}

/**
 * Pipeline panel — renders data from a data pipeline.
 */
class PipelinePanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: config.title || 'Data', icon: '📊', type: 'pipeline', ...config });
    this.pipeline = config.pipeline || null;
    this.data = null;
  }

  renderContent(el) {
    el.innerHTML = `<div class="pipeline-data">
      <div class="panel-empty">
        <span class="panel-empty-icon">📊</span>
        <span class="panel-empty-text">Awaiting data pipeline</span>
        <span class="panel-empty-hint">Data will render when the pipeline connects</span>
      </div>
    </div>`;
  }

  /**
   * Called by the pipeline system when new data arrives.
   *
   * @param {object} data - Transformed data from pipeline
   */
  onPipelineData(data) {
    this.data = data;
    const container = this.el?.querySelector('.pipeline-data');
    if (!container) return;

    if (typeof data === 'string') {
      container.textContent = data;
    } else if (Array.isArray(data)) {
      container.innerHTML = data
        .map((item) => `<div class="pipeline-item">${this._formatItem(item)}</div>`)
        .join('');
    } else if (data && typeof data === 'object') {
      container.innerHTML = Object.entries(data)
        .map(([k, v]) => `<div class="pipeline-kv"><strong>${_escapeHtml(k)}:</strong> ${_escapeHtml(String(v))}</div>`)
        .join('');
    }
  }

  _formatItem(item) {
    if (typeof item === 'string') return _escapeHtml(item);
    if (typeof item === 'object') {
      return Object.entries(item)
        .map(([k, v]) => `<span class="kv-key">${_escapeHtml(k)}:</span> ${_escapeHtml(String(v))}`)
        .join(' · ');
    }
    return _escapeHtml(String(item));
  }
}

/**
 * Status Strip panel — persistent ambient info bar.
 */
class StatusStripPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: 'Status', icon: '📌', type: 'status-strip', ...config });
    this.items = new Map();
  }

  renderContent(el) {
    el.className += ' status-strip-content';
    el.innerHTML = '<div class="status-items"></div>';
  }

  /**
   * Update a status item.
   *
   * @param {string} key - Item key (e.g., 'calendar', 'email', 'weather')
   * @param {object} data - { icon, label, value, detail }
   */
  updateItem(key, data) {
    this.items.set(key, { ...data, updated: Date.now() });
    this._renderItems();
  }

  _setupSubscriptions() {
    this._addSubscription(
      { type: 'event', event: 'status.' },
      (msg) => {
        const event = msg.payload?.event || '';
        const key = event.replace('status.', '');
        this.updateItem(key, msg.payload?.data || {});
      }
    );
  }

  _renderItems() {
    const container = this.el?.querySelector('.status-items');
    if (!container) return;

    container.innerHTML = '';
    for (const [key, item] of this.items) {
      const el = document.createElement('div');
      el.className = 'status-item';
      el.dataset.key = key;
      el.innerHTML = `
        <span class="status-icon">${item.icon || '•'}</span>
        <span class="status-label">${_escapeHtml(item.label || key)}</span>
        <span class="status-value">${_escapeHtml(item.value || '')}</span>
      `;
      el.title = item.detail || '';
      container.appendChild(el);
    }
  }
}

// ============================================================
// PANEL REGISTRY
// ============================================================

const PANEL_TYPES = {
  chat: ChatPanel,
  'brain-status': BrainStatusPanel,
  'task-list': TaskListPanel,
  'bus-monitor': BusMonitorPanel,
  pipeline: PipelinePanel,
  'status-strip': StatusStripPanel,
};

/**
 * Create a panel by type name.
 *
 * @param {string} type - Panel type from PANEL_TYPES
 * @param {string} id - Panel id
 * @param {object} config - Configuration
 * @returns {BasePanel}
 */
function createPanel(type, id, config = {}) {
  const PanelClass = PANEL_TYPES[type] || BasePanel;
  return new PanelClass(id, { type, ...config });
}

/**
 * Register a custom panel type.
 *
 * @param {string} type - Type name
 * @param {typeof BasePanel} PanelClass - Panel class
 */
function registerPanelType(type, PanelClass) {
  PANEL_TYPES[type] = PanelClass;
}

// ============================================================
// EXPORTS
// ============================================================

export {
  BasePanel,
  ChatPanel,
  BrainStatusPanel,
  TaskListPanel,
  BusMonitorPanel,
  PipelinePanel,
  StatusStripPanel,
  PANEL_TYPES,
  createPanel,
  registerPanelType,
};
