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
      (msg) => this.addMessage(msg.payload, !!msg._replay)
    );
  }

  addMessage(data, isReplay = false) {
    const container = this.el?.querySelector('.chat-messages');
    if (!container) return;

    const role = data.role || 'system';
    const text = data.text || data.content || '';

    // Dedup: use a set of content hashes to prevent duplicate messages
    // (from WS reconnect replays, buffer replays, etc.)
    if (!this._seenHashes) this._seenHashes = new Set();
    const hash = `${role}:${text.slice(0, 200)}`;
    if (this._seenHashes.has(hash)) return;
    this._seenHashes.add(hash);

    // Clear empty state on first message
    const empty = container.querySelector('.panel-empty');
    if (empty) empty.remove();
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
    const msgType = msg.type || '';
    const brainName = msg.payload?.brain || msg.payload?.target_brain || msg.source;
    
    if (!brainName || brainName === '*') return;
    // Don't show internal components — only worker brains (python_brain_*, researcher)
    if (brainName.startsWith('orchestrator')) return;
    if (brainName === 'front_brain') return;
    if (brainName === 'bigbrain_system') return;
    if (brainName === 'focus_bridge') return;
    if (brainName === 'web_adapter' || brainName === 'morphable_ui') return;

    let status = 'idle';
    let stage = '';

    // PROGRESS messages always mean the brain is busy
    if (msgType === 'progress') {
      status = 'busy';
      stage = msg.payload?.stage || '';
    } else if (event === 'brain.started' || event === 'brain.stopped') {
      // Registration/shutdown events — brain is idle (available) or gone
      status = event === 'brain.started' ? 'idle' : 'offline';
    } else if (event.includes('started') || event.includes('received')) {
      // subtask.started, task.received — brain is actually working
      status = 'busy';
    } else if (event.includes('complete') && !event.includes('task.complete')) {
      // subtask.complete / brain.complete → brain goes idle
      status = 'idle';
    } else if (event.includes('error') || event.includes('failed')) {
      status = 'error';
    } else if (event.includes('task.complete') || event.includes('task.failed')) {
      // task-level events: update orchestrator status, not individual brains
      const orch = msg.source || 'orchestrator';
      this.brains.set(orch, {
        status: event.includes('failed') ? 'error' : 'idle',
        stage: '',
        updated: Date.now(),
      });
      this._renderBrains();
      return;
    }

    this.brains.set(brainName, {
      status,
      stage,
      updated: Date.now(),
    });

    this._renderBrains();
  }

  _renderBrains() {
    const list = this.el?.querySelector('.brain-list');
    if (!list) return;

    list.innerHTML = '';
    for (const [name, info] of this.brains) {
      const statusLabel = { idle: 'Ready', busy: 'Working', error: 'Error', offline: 'Offline' }[info.status] || 'Unknown';

      const prettyName = name.replace(/_/g, ' ');
      const stageText = info.stage ? info.stage.replace(/_/g, ' ') : '';

      const item = document.createElement('div');
      item.className = `brain-item brain-${info.status}`;
      item.innerHTML = `
        <span class="brain-indicator"></span>
        <span class="brain-name">${_escapeHtml(prettyName)}</span>
        ${stageText ? `<span class="brain-task">${_escapeHtml(stageText)}</span>` : ''}
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
    this._removeTimers = new Map();
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

  /** Extract a human-readable label from a bus message payload. */
  _extractLabel(msg, fallback) {
    const p = msg.payload || {};
    // Priority: description > request (truncated) > brain name > fallback
    if (p.description) return p.description;
    if (p.request) return p.request.length > 60 ? p.request.slice(0, 57) + '...' : p.request;
    if (p.brain && p.brain !== 'subtask') {
      const pretty = p.brain.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return pretty;
    }
    return fallback || 'Task';
  }

  /** Schedule auto-removal of completed/failed tasks after delay. */
  _scheduleRemoval(taskId, delayMs = 8000) {
    if (this._removeTimers.has(taskId)) clearTimeout(this._removeTimers.get(taskId));
    this._removeTimers.set(taskId, setTimeout(() => {
      this.tasks.delete(taskId);
      this._removeTimers.delete(taskId);
      this._renderTasks();
    }, delayMs));
  }

  _setupSubscriptions() {
    // RESULT messages — match by reply_to
    this._addSubscription({ type: 'result' }, (msg) => {
      const taskId = msg.reply_to;
      if (taskId && this.tasks.has(taskId)) {
        const task = this.tasks.get(taskId);
        task.status = msg.payload?.success ? 'complete' : 'failed';
        task.progress = 100;
        this._renderTasks();
        this._scheduleRemoval(taskId);
      }
    });

    // Planning phase events (assessment, architect, project_structure)
    this._addSubscription({ type: 'event', event: 'planning.' }, (msg) => {
      const event = msg.payload?.event || '';
      const planningId = msg.id || 'planning';
      if (event === 'planning.assessment') {
        this.tasks.set(planningId, {
          id: planningId,
          planId: planningId,
          label: 'Analyzing task...',
          target: msg.source,
          status: 'running',
          progress: -1,
          started: Date.now(),
        });
        this._renderTasks();
      } else if (event === 'planning.architect_started') {
        // Update or create planning entry
        const existing = this.tasks.get(planningId) || [...this.tasks.values()].find(t => t.label === 'Analyzing task...');
        const id = existing?.id || planningId;
        this.tasks.set(id, {
          ...(existing || {}),
          id,
          planId: id,
          label: 'Designing architecture...',
          target: msg.source,
          status: 'running',
          progress: -1,
          started: existing?.started || Date.now(),
        });
        this._renderTasks();
      } else if (event === 'planning.project_structure') {
        // Architecture done — remove planning entry (task.received will replace it)
        for (const [tid, task] of this.tasks) {
          if (task.label === 'Designing architecture...' || task.label === 'Analyzing task...') {
            this.tasks.delete(tid);
          }
        }
        this._renderTasks();
      }
    });

    // Orchestrator events (task.received, task.complete, task.failed)
    this._addSubscription({ type: 'event', event: 'task.' }, (msg) => {
      const event = msg.payload?.event || '';
      const taskId = msg.payload?.task_id || msg.id;
      if (event.includes('received') || event.includes('started')) {
        this.tasks.set(taskId, {
          id: taskId,
          planId: taskId,  // Track plan ID for task.complete matching
          label: this._extractLabel(msg, 'Planning'),
          target: msg.source || msg.target,
          status: 'running',
          progress: -1,
          started: Date.now(),
        });
        this._renderTasks();
      } else if (event.includes('complete') || event.includes('failed')) {
        const isFail = event.includes('failed') || event.includes('cancelled');
        const newStatus = isFail ? 'failed' : 'complete';

        // Direct match by task_id (plan ID)
        if (this.tasks.has(taskId)) {
          this.tasks.get(taskId).status = newStatus;
          this.tasks.get(taskId).progress = 100;
          this._renderTasks();
          this._scheduleRemoval(taskId, isFail ? 12000 : 8000);
        }

        // Also mark ALL subtasks belonging to this plan as complete.
        // This handles cases where subtask.complete was missed (WS disconnect).
        for (const [sid, task] of this.tasks) {
          if (task.planId === taskId && task.status === 'running') {
            task.status = newStatus;
            task.progress = 100;
            this._scheduleRemoval(sid, isFail ? 12000 : 8000);
          }
        }
        this._renderTasks();
      }
    });

    // Subtask events (subtask.started, subtask.complete, subtask.failed)
    this._addSubscription({ type: 'event', event: 'subtask.' }, (msg) => {
      const event = msg.payload?.event || '';
      const subtaskId = msg.payload?.subtask_id || msg.id;
      const planId = msg.payload?.task_id;  // Parent plan ID

      if (event.includes('started')) {
        // Remove parent "Planning" task entry — subtasks replace it
        if (planId && this.tasks.has(planId)) {
          if (this._removeTimers.has(planId)) clearTimeout(this._removeTimers.get(planId));
          this._removeTimers.delete(planId);
          this.tasks.delete(planId);
        }

        this.tasks.set(subtaskId, {
          id: subtaskId,
          planId: planId,  // Link subtask to its parent plan
          label: this._extractLabel(msg),
          target: msg.payload?.brain || msg.target,
          status: 'running',
          progress: -1,
          started: Date.now(),
        });
        this._renderTasks();
      } else if (event.includes('complete') || event.includes('failed')) {
        if (this.tasks.has(subtaskId)) {
          const task = this.tasks.get(subtaskId);
          task.status = event.includes('complete') ? 'complete' : 'failed';
          task.progress = 100;
          this._renderTasks();
          this._scheduleRemoval(subtaskId);
        }
      }
    });

    // Explicit progress updates — match by reply_to, subtask_id, or brain source
    this._addSubscription(
      { type: 'progress' },
      (msg) => {
        const p = msg.payload || {};
        // Try multiple correlation keys
        const candidates = [msg.reply_to, p.task_id, p.subtask_id];
        let task = null;
        for (const cid of candidates) {
          if (cid && this.tasks.has(cid)) { task = this.tasks.get(cid); break; }
        }
        // Fallback: match by brain name (source) — find first running task assigned to this brain
        if (!task && msg.source) {
          for (const [, t] of this.tasks) {
            if (t.status === 'running' && t.target === msg.source) { task = t; break; }
          }
        }
        if (task) {
          // Don't overwrite completed/failed tasks with late progress events
          if (task.status === 'complete' || task.status === 'failed') return;
          // Use explicit progress if provided, otherwise estimate from stage
          if (typeof p.progress === 'number') {
            task.progress = p.progress;
          } else if (p.stage) {
            task.progress = TaskListPanel._estimateProgress(p.stage);
          }
          if (p.stage) task.stage = p.stage;
          task.status = 'running';
          this._renderTasks();
        }
      }
    );
  }

  /** Map brain stage names to approximate progress percentages. */
  static _estimateProgress(stage) {
    const stageMap = {
      // Researcher stages
      'planning': 15,
      'searching': 35,
      'search_complete': 55,
      'triangulated': 65,
      'summarizing': 80,
      // PythonBrain stages
      'generating_code': 25,
      'executing': 60,
      'completed': 90,
      'succeeded': 95,
      'retrying': 40,
      'failed_after_retries': 100,
    };
    return stageMap[stage] || -1;  // -1 = indeterminate for unknown stages
  }

  _renderTasks() {
    const list = this.el?.querySelector('.task-list');
    if (!list) return;

    if (this.tasks.size === 0) {
      list.innerHTML = `
        <div class="panel-empty">
          <span class="panel-empty-icon">📋</span>
          <span class="panel-empty-text">No active tasks</span>
          <span class="panel-empty-hint">Send a message to start a task</span>
        </div>`;
      return;
    }

    list.innerHTML = '';
    for (const [, task] of this.tasks) {
      const icon = { running: '⏳', complete: '✅', failed: '❌' }[task.status] || '⏳';
      const statusLabel = { running: 'Running', complete: 'Done', failed: 'Failed' }[task.status] || 'Pending';
      const isIndeterminate = task.status === 'running' && task.progress < 0;

      const stageText = task.stage ? ` — ${task.stage}` : '';
      const targetLine = task.target ? `<span class="task-target">${_escapeHtml(task.target)}${_escapeHtml(stageText)}</span>` : '';

      const item = document.createElement('div');
      item.className = `task-item task-${task.status}`;
      item.innerHTML = `
        <div class="task-item-header">
          <span class="task-icon">${icon}</span>
          <span class="task-type">${_escapeHtml(task.label)}</span>
          <span class="task-status-badge">${statusLabel}</span>
        </div>
        ${targetLine ? `<div style="padding-left:24px">${targetLine}</div>` : ''}
        <div class="task-progress-bar${isIndeterminate ? ' task-progress-indeterminate' : ''}">
          <div class="task-progress-fill" style="width:${isIndeterminate ? '30' : task.progress}%"></div>
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
 * Code Output panel — shows code execution results from PythonBrain.
 */
class CodeOutputPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: 'Code Output', icon: '💻', type: 'code-output', ...config });
    this.results = [];
    this._seenIds = new Set(); // dedup results from global buffer + panel subscription
  }

  renderContent(el) {
    el.innerHTML = `<div class="code-output-list">
      <div class="panel-empty">
        <span class="panel-empty-icon">💻</span>
        <span class="panel-empty-text">Code output will appear here</span>
        <span class="panel-empty-hint">Send a coding task to see results</span>
      </div>
    </div>`;
  }

  _setupSubscriptions() {
    // Listen for RESULT messages from python brains
    this._addSubscription({ type: 'result' }, (msg) => {
      const src = (msg.source || '').toLowerCase();
      if (src.includes('python')) {
        this._addResult(msg);
      }
      // Also catch orchestrator-aggregated results containing python data
      // (handles WS reconnect replays where the direct brain result was missed)
      if (src.includes('orchestrator') && msg.payload?.results) {
        for (const [, val] of Object.entries(msg.payload.results)) {
          if (!val || typeof val !== 'object') continue;
          const data = val.data || val;
          if (data.stdout || data.generated_code) {
            const synth = { ...msg, payload: data, source: 'python_brain', _synthetic: true };
            this._addResult(synth);
          }
        }
      }
    });

    // Listen for progress updates
    this._addSubscription({ type: 'progress' }, (msg) => {
      const src = (msg.source || '').toLowerCase();
      if (src.includes('python')) {
        this._updateProgress(msg);
      }
    });
  }

  _addResult(msg) {
    // Dedup: global buffer + panel subscription can both deliver
    const msgId = msg.id || msg.reply_to || `${msg.source}-${msg.timestamp}`;
    if (this._seenIds.has(msgId)) return;
    this._seenIds.add(msgId);

    const payload = msg.payload || {};
    // Result data may be nested under payload.data (PythonBrain) or flat
    const data = payload.data || payload;
    const container = this.el?.querySelector('.code-output-list');
    if (!container) return;

    const empty = container.querySelector('.panel-empty');
    if (empty) empty.remove();

    const code = data.generated_code || '';
    const stdout = data.stdout || data.output || '';
    const stderr = data.stderr || '';
    const success = data.success !== false && payload.success !== false;
    const time = _timestamp('HH:mm:ss');

    const result = document.createElement('div');
    result.className = `code-result ${success ? 'code-result-ok' : 'code-result-err'}`;

    let html = `<div class="code-result-header">
      <span class="code-result-status">${success ? '✅' : '❌'}</span>
      <span class="code-result-time">${time}</span>
    </div>`;

    if (code) {
      // Detect language from content heuristics
      const lang = CodeOutputPanel._detectLang(code);
      html += `<div class="code-block-wrap">
        <div class="code-block-header">
          <span class="code-lang-badge">${lang}</span>
          <button class="code-copy-btn" title="Copy code">📋</button>
        </div>
        <pre class="code-block"><code class="language-${lang}">${_escapeHtml(code)}</code></pre>
      </div>`;
    }

    if (stdout) {
      html += `<div class="code-stdout-label">Output</div>
               <pre class="code-stdout"><code class="language-text">${_escapeHtml(stdout)}</code></pre>`;
    }

    if (stderr) {
      html += `<div class="code-stderr-label">Errors</div>
               <pre class="code-stderr">${_escapeHtml(stderr)}</pre>`;
    }

    if (!code && !stdout && !stderr) {
      html += `<div class="code-stdout-label">${success ? 'Completed (no output)' : 'Failed (no details)'}</div>`;
    }

    result.innerHTML = html;

    // Wire up copy button
    const copyBtn = result.querySelector('.code-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(code).then(() => {
          copyBtn.textContent = '✅';
          setTimeout(() => { copyBtn.textContent = '📋'; }, 1500);
        });
      });
    }

    container.appendChild(result);

    // Run Prism highlighting on the new code blocks
    if (window.Prism) {
      result.querySelectorAll('pre code[class*="language-"]').forEach(el => {
        window.Prism.highlightElement(el);
      });
    }

    container.scrollTop = container.scrollHeight;

    this.results.push({ code, stdout, stderr, success, time: Date.now() });

    // Keep max 20 results
    while (this.results.length > 20 && container.children.length > 20) {
      container.removeChild(container.firstChild);
      this.results.shift();
    }
  }

  _updateProgress(msg) {
    const stage = msg.payload?.stage || '';
    if (stage) {
      const label = stage.replace(/_/g, ' ');
      this.setTitle(`Code Output — ${label}`);
    }
  }

  /** Detect programming language from code content. */
  static _detectLang(code) {
    const trimmed = code.trim();
    // Shebang
    if (trimmed.startsWith('#!/usr/bin/env python') || trimmed.startsWith('#!/usr/bin/python')) return 'python';
    if (trimmed.startsWith('#!/bin/bash') || trimmed.startsWith('#!/bin/sh')) return 'bash';
    // Python signals
    if (/^(import |from |def |class |async def |if __name__)/m.test(trimmed)) return 'python';
    if (/^\s*(print\(|raise |yield |lambda )/m.test(trimmed)) return 'python';
    // JavaScript/Node
    if (/^(const |let |var |function |import |export |require\(|module\.exports)/m.test(trimmed)) return 'javascript';
    // HTML
    if (/^<!DOCTYPE|^<html|^<div|^<head/im.test(trimmed)) return 'markup';
    // CSS
    if (/^[.#@][\w-]+\s*\{|^body\s*\{|^:root\s*\{/m.test(trimmed)) return 'css';
    // JSON
    if ((trimmed.startsWith('{') || trimmed.startsWith('[')) && (trimmed.endsWith('}') || trimmed.endsWith(']'))) {
      try { JSON.parse(trimmed); return 'json'; } catch { /* not json */ }
    }
    // Bash signals
    if (/^(echo |curl |wget |apt |pip |npm |cd |ls |mkdir |chmod )/m.test(trimmed)) return 'bash';
    // Default: Python (BigBrain's primary brain)
    return 'python';
  }
}

/**
 * Research Results panel — shows findings from ResearcherBrain.
 */
class ResearchResultsPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { title: 'Research', icon: '🔍', type: 'research-results', ...config });
    this.findings = [];
    this._seenIds = new Set();
  }

  renderContent(el) {
    el.innerHTML = `<div class="research-list">
      <div class="panel-empty">
        <span class="panel-empty-icon">🔍</span>
        <span class="panel-empty-text">Research results will appear here</span>
        <span class="panel-empty-hint">Ask BigBrain to research a topic</span>
      </div>
    </div>`;
  }

  _setupSubscriptions() {
    this._addSubscription({ type: 'result' }, (msg) => {
      const src = (msg.source || '').toLowerCase();
      if (src.includes('research')) {
        this._addFinding(msg);
      }
      // Also catch orchestrator-aggregated results containing research data
      if (src.includes('orchestrator') && msg.payload?.results) {
        for (const [, val] of Object.entries(msg.payload.results)) {
          if (!val || typeof val !== 'object') continue;
          const data = val.data || val;
          if (data.summary || data.answer || data.top_sources) {
            const synth = { ...msg, payload: data, source: 'researcher', _synthetic: true };
            this._addFinding(synth);
          }
        }
      }
    });

    this._addSubscription({ type: 'progress' }, (msg) => {
      const src = (msg.source || '').toLowerCase();
      if (src.includes('research')) {
        this._updateProgress(msg);
      }
    });
  }

  _addFinding(msg) {
    const msgId = msg.id || msg.reply_to || `${msg.source}-${msg.timestamp}`;
    if (this._seenIds.has(msgId)) return;
    this._seenIds.add(msgId);

    const payload = msg.payload || {};
    // ResearcherBrain nests output under payload.data (same as PythonBrain)
    const data = payload.data || payload;
    const container = this.el?.querySelector('.research-list');
    if (!container) return;

    const empty = container.querySelector('.panel-empty');
    if (empty) empty.remove();

    const summary = data.summary || data.text || data.content || '';
    const sources = data.sources || data.top_sources || [];
    const query = data.query || data.queries_used?.[0] || '';
    const time = _timestamp('HH:mm:ss');

    const finding = document.createElement('div');
    finding.className = 'research-finding';

    let html = `<div class="research-finding-header">
      <span class="research-finding-icon">📄</span>
      ${query ? `<span class="research-query">${_escapeHtml(query)}</span>` : ''}
      <span class="research-finding-time">${time}</span>
    </div>`;

    if (summary) {
      html += `<div class="research-summary">${this._renderMarkdown(summary)}</div>`;
    } else {
      html += `<div class="research-summary">${_escapeHtml(JSON.stringify(data).slice(0, 300))}</div>`;
    }

    if (sources.length > 0) {
      html += '<div class="research-sources"><div class="research-sources-title">Sources</div>';
      for (let i = 0; i < Math.min(sources.length, 8); i++) {
        const src = sources[i];
        const title = typeof src === 'string' ? src : (src.title || src.name || '');
        const url = typeof src === 'object' ? (src.url || src.link || '') : '';
        const snippet = typeof src === 'object' ? (src.snippet || src.excerpt || '') : '';

        if (url) {
          html += `<a class="research-source-link" href="${_escapeHtml(url)}" target="_blank" rel="noopener">
            <span class="research-source-num">[${i + 1}]</span>
            <span class="research-source-title">${_escapeHtml(title || url)}</span>
            ${snippet ? `<span class="research-source-snippet">${_escapeHtml(snippet.slice(0, 120))}</span>` : ''}
          </a>`;
        } else {
          html += `<div class="research-source-link">
            <span class="research-source-num">[${i + 1}]</span>
            <span class="research-source-title">${_escapeHtml(title || String(src))}</span>
          </div>`;
        }
      }
      html += '</div>';
    }

    finding.innerHTML = html;
    container.appendChild(finding);
    container.scrollTop = container.scrollHeight;

    this.findings.push({ summary, sources, query, time: Date.now() });
  }

  /** Markdown-to-HTML for research summaries — with links, structure, and citations. */
  _renderMarkdown(text) {
    let html = _escapeHtml(text);

    // Headers: ## Title → styled header
    html = html.replace(/^#{1,2}\s+(.+)$/gm, '<div class="research-heading">$1</div>');
    html = html.replace(/^###\s+(.+)$/gm, '<div class="research-subheading">$1</div>');

    // Bold: **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Italic: *text*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // Inline code: `code`
    html = html.replace(/`([^`]+)`/g, '<code class="research-code">$1</code>');

    // Bullet lists: - item → styled item
    html = html.replace(/^[-•]\s+(.+)$/gm, '<div class="research-bullet">• $1</div>');
    // Numbered lists: 1. item
    html = html.replace(/^\d+\.\s+(.+)$/gm, '<div class="research-bullet-num">$&</div>');

    // Citations: [1] [2] etc — clickable superscripts
    html = html.replace(/\[(\d+)\]/g, '<sup class="research-cite">[$1]</sup>');

    // URLs: detect bare URLs and make them clickable
    html = html.replace(
      /(?:https?:\/\/)[^\s<>&"]+/g,
      (url) => `<a class="research-link" href="${url}" target="_blank" rel="noopener">${url}</a>`
    );

    // Double line breaks → paragraph spacing, single → <br>
    html = html.replace(/\n\n/g, '</p><p class="research-para">');
    html = html.replace(/\n/g, '<br>');
    html = `<p class="research-para">${html}</p>`;

    return html;
  }

  _updateProgress(msg) {
    const stage = msg.payload?.stage || '';
    if (stage) {
      const label = stage.replace(/_/g, ' ');
      this.setTitle(`Research — ${label}`);
    }
  }
}

/**
 * Placeholder panel — "Coming soon" for unimplemented workspace features.
 */
class PlaceholderPanel extends BasePanel {
  constructor(id, config = {}) {
    super(id, { type: 'placeholder', ...config });
  }

  renderContent(el) {
    el.innerHTML = `<div class="panel-empty">
      <span class="panel-empty-icon">${this.icon}</span>
      <span class="panel-empty-text">${_escapeHtml(this.title)}</span>
      <span class="panel-empty-hint">Coming soon</span>
    </div>`;
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
  'code-output': CodeOutputPanel,
  'research-results': ResearchResultsPanel,
  placeholder: PlaceholderPanel,
  // Aliases: workspace panel names → best available implementation
  editor: PlaceholderPanel,
  repl: CodeOutputPanel,
  terminal: BusMonitorPanel,
  preview: PlaceholderPanel,
  devtools: PlaceholderPanel,
  camera: PlaceholderPanel,
  'klipper-status': PlaceholderPanel,
  'gcode-viewer': PlaceholderPanel,
  schematic: PlaceholderPanel,
  pinout: PlaceholderPanel,
  browser: PlaceholderPanel,
  notes: PlaceholderPanel,
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
  CodeOutputPanel,
  ResearchResultsPanel,
  PlaceholderPanel,
  PANEL_TYPES,
  createPanel,
  registerPanelType,
};
