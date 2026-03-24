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
      <span class="panel-title">${this.title}</span>
      <span class="panel-actions">
        <button class="panel-btn panel-btn-collapse" title="Toggle collapse">▾</button>
      </span>
    `;

    // Click title bar to toggle collapse
    titleBar.addEventListener('click', (e) => {
      if (e.target.closest('.panel-btn')) return; // Let button handlers run
      this.el.classList.toggle('panel-collapsed');
      this._onCollapseToggle();
    });

    // Collapse button
    const collapseBtn = titleBar.querySelector('.panel-btn-collapse');
    collapseBtn.addEventListener('click', () => {
      this.el.classList.toggle('panel-collapsed');
      this._onCollapseToggle();
    });

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
    contentEl.textContent = 'Empty panel';
  }

  /**
   * Subscribe to bus events.
   *
   * @param {BusClient} busClient - WebSocket bus client
   */
  subscribe(busClient) {
    this._busClient = busClient;
    // Subclass should override to add specific subscriptions
    this._setupSubscriptions();
  }

  /**
   * Override to set up bus subscriptions.
   * Use this._addSubscription(filter, handler).
   */
  _setupSubscriptions() {
    // Default: no subscriptions
  }

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
  onEvent(event) {
    // Override in subclass
  }

  /**
   * Unmount and cleanup.
   */
  unmount() {
    // Remove bus subscriptions
    for (const sub of this._subscriptions) {
      if (this._busClient) {
        this._busClient.off(sub.filter, sub.handler);
      }
    }
    this._subscriptions = [];
    this._busClient = null;

    // Remove DOM
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

  _onCollapseToggle() {
    const btn = this.el.querySelector('.panel-btn-collapse');
    const collapsed = this.el.classList.contains('panel-collapsed');
    if (btn) btn.textContent = collapsed ? '▸' : '▾';
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
      <div class="chat-messages" id="chat-${this.id}"></div>
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

    const role = data.role || 'system';
    const text = data.text || data.content || '';

    const msgEl = document.createElement('div');
    msgEl.className = `chat-msg chat-msg-${role}`;
    msgEl.textContent = text;
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
    el.innerHTML = '<div class="brain-list"></div>';
  }

  _setupSubscriptions() {
    this._addSubscription(
      { type: 'event', event: 'brain.' },
      (msg) => this._handleBrainEvent(msg)
    );
    this._addSubscription(
      { type: 'state', event: 'brain.' },
      (msg) => this._handleBrainEvent(msg)
    );
  }

  _handleBrainEvent(msg) {
    const event = msg.payload?.event || '';
    const brainName = msg.payload?.brain || msg.source;
    let status = 'idle';

    if (event.includes('started')) status = 'busy';
    else if (event.includes('complete')) status = 'idle';
    else if (event.includes('error')) status = 'error';
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
      const item = document.createElement('div');
      item.className = `brain-item brain-${info.status}`;
      const indicator = { idle: '🟢', busy: '🟡', error: '🔴' }[info.status] || '⚪';
      item.innerHTML = `
        <span class="brain-indicator">${indicator}</span>
        <span class="brain-name">${name}</span>
        <span class="brain-task">${info.task}</span>
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
    el.innerHTML = '<div class="task-list"></div>';
  }

  _setupSubscriptions() {
    this._addSubscription({ type: 'task' }, (msg) => {
      this.tasks.set(msg.id, {
        id: msg.id,
        type: msg.payload?.type || 'unknown',
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
    this._addSubscription(
      { type: 'state', event: 'brain.progress' },
      (msg) => {
        const taskId = msg.payload?.task_id;
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
      const item = document.createElement('div');
      const icon = { running: '⏳', complete: '✅', failed: '❌' }[task.status] || '⏳';
      item.className = `task-item task-${task.status}`;
      item.innerHTML = `
        <span class="task-icon">${icon}</span>
        <span class="task-type">${task.type}</span>
        <span class="task-target">${task.target}</span>
        <div class="task-progress-bar">
          <div class="task-progress-fill" style="width: ${task.progress}%"></div>
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
    el.innerHTML = '<div class="bus-messages"></div>';
  }

  _setupSubscriptions() {
    // Subscribe to ALL messages
    this._addSubscription({}, (msg) => this._addMessage(msg));
  }

  _addMessage(msg) {
    const container = this.el?.querySelector('.bus-messages');
    if (!container) return;

    const type = msg.type?.toUpperCase?.() || msg.type || 'EVENT';
    const source = msg.source || '?';
    const target = msg.target || '*';
    const event = msg.payload?.event || msg.payload?.type || '';

    const msgEl = document.createElement('div');
    msgEl.className = `bus-msg bus-msg-${type.toLowerCase()}`;
    msgEl.innerHTML = `
      <span class="bus-type">${type}</span>
      <span class="bus-route">${source} → ${target}</span>
      <span class="bus-event">${event}</span>
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
 * Generic container that displays whatever data its pipeline provides.
 */
class PipelinePanel extends BasePanel {
  /**
   * @param {string} id
   * @param {object} config
   * @param {object} config.pipeline - Pipeline definition
   */
  constructor(id, config = {}) {
    super(id, { title: config.title || 'Data', icon: '📊', type: 'pipeline', ...config });
    this.pipeline = config.pipeline || null;
    this.data = null;
  }

  renderContent(el) {
    el.innerHTML = '<div class="pipeline-data"><em>Waiting for data...</em></div>';
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

    // Render based on data shape
    if (typeof data === 'string') {
      container.textContent = data;
    } else if (Array.isArray(data)) {
      container.innerHTML = data
        .map((item) => `<div class="pipeline-item">${this._formatItem(item)}</div>`)
        .join('');
    } else if (data && typeof data === 'object') {
      container.innerHTML = Object.entries(data)
        .map(([k, v]) => `<div class="pipeline-kv"><strong>${k}:</strong> ${v}</div>`)
        .join('');
    }
  }

  _formatItem(item) {
    if (typeof item === 'string') return item;
    if (typeof item === 'object') {
      return Object.entries(item)
        .map(([k, v]) => `<span class="kv-key">${k}:</span> ${v}`)
        .join(' · ');
    }
    return String(item);
  }
}

/**
 * Status Strip panel — persistent ambient info bar.
 * Displays calendar next event, unread email count, weather, etc.
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
        <span class="status-label">${item.label || key}</span>
        <span class="status-value">${item.value || ''}</span>
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
