/**
 * app.js — BigBrain Morphable UI Application
 *
 * Main orchestrator that wires together:
 *   - BusClient (WebSocket connection to Python bus)
 *   - SlotManager (layout catalog + grid management)
 *   - Panel system (autonomous bus subscribers)
 *   - Pipeline system (data pipelines)
 *   - FLIP engine (smooth layout transitions)
 *   - Focus state (shared between Front Brain and UI)
 */

import { snapshotPanels, flipPanels, highlightPanel, MorphThrottle, getSpringCSS } from './morph.js?v=20260327b';
import { LAYOUT_CATALOG, SlotManager, WORKSPACE_DEFAULTS, WORKSPACE_LABELS } from './layout.js?v=20260327b';
import { createPanel, registerPanelType, StatusStripPanel } from './panel.js?v=20260327b';
import { BusClient } from './bus-client.js?v=20260327b';
import { PipelineManager } from './pipeline.js?v=20260327b';

// ============================================================
// APPLICATION STATE
// ============================================================

class MorphableUI {
  constructor() {
    // DOM references
    this.gridContainer = null;
    this.statusStrip = null;
    this.chatInput = null;
    this.connectionIndicator = null;

    // Core systems
    this.bus = null;
    this.slotManager = null;
    this.pipelineManager = null;
    this.morphThrottle = new MorphThrottle(800); // Max 1 morph per 800ms

    // State
    this.currentWorkspace = null;
    this.focusState = {
      workspaces: {},
      mode: 'normal',
    };
    this.panels = new Map();  // panelId -> BasePanel
    this._initialized = false;

    // Persistent panels survive workspace switches (chat, task-list)
    this._persistentPanels = new Map(); // type -> { panel, busConnected }

    // Global result buffers (for panels that only exist in specific workspaces)
    this._codeResults = [];      // buffered python_brain results
    this._researchFindings = []; // buffered researcher results
  }

  /**
   * Initialize the Morphable UI.
   *
   * @param {object} opts
   * @param {string} opts.wsUrl - WebSocket URL for bus connection
   * @param {string} [opts.workspace='default'] - Initial workspace
   */
  async init(opts = {}) {
    const { wsUrl, workspace = 'default' } = opts;

    // Get DOM refs
    this.gridContainer = document.getElementById('grid-container');
    this.statusStrip = document.getElementById('status-strip');
    this.chatInput = document.getElementById('chat-input');
    this.connectionIndicator = document.getElementById('connection-status');

    if (!this.gridContainer) {
      console.error('MorphableUI: #grid-container not found');
      return;
    }

    // Initialize SlotManager
    this.slotManager = new SlotManager(this.gridContainer);

    // Connect to bus (pass WS auth token if present)
    const wsToken = document.body.dataset.wsToken || null;
    this.bus = new BusClient(wsUrl || this._defaultWsUrl(), { token: wsToken });
    this.bus.onConnect = () => this._onBusConnect();
    this.bus.onDisconnect = () => this._onBusDisconnect();
    this.bus.connect();

    // Pipeline manager
    this.pipelineManager = new PipelineManager(this.bus);

    // Initialize status strip
    this._initStatusStrip();

    // Set up chat input
    this._initChatInput();

    // ---- Panel collapse: coordinate FLIP + grid adaptation ----
    this.gridContainer.addEventListener('panel-collapse-toggle', (e) => {
      this._handleCollapseToggle(e.detail.panelId);
    });

    // Listen for focus state changes from the server
    this.bus.on({ type: 'state', event: 'focus.' }, (msg) => {
      this._handleFocusChange(msg.payload);
    });

    // Listen for workspace switch commands from agent
    this.bus.on({ type: 'event', event: 'ui.workspace' }, (msg) => {
      this.switchWorkspace(msg.payload?.workspace);
    });

    // Listen for panel visibility commands from agent
    this.bus.on({ type: 'event', event: 'ui.panel.' }, (msg) => {
      this._handlePanelCommand(msg.payload);
    });

    // Listen for pipeline commands from agent
    this.bus.on({ type: 'event', event: 'ui.pipeline.' }, (msg) => {
      this._handlePipelineCommand(msg.payload);
    });

    // Listen for highlight commands
    this.bus.on({ type: 'event', event: 'ui.highlight' }, (msg) => {
      const panelId = msg.payload?.panel;
      const panel = this.panels.get(panelId);
      if (panel?.el) {
        highlightPanel(panel.el, msg.payload?.color);
      }
    });

    // Listen for workspace highlight (task complete → pulse the tab)
    this.bus.on({ type: 'event', event: 'workspace.highlight' }, (msg) => {
      const ws = msg.payload?.workspace;
      if (ws) this._pulseWorkspaceTab(ws);
    });

    // Global result buffering — catch results even when target panel doesn't exist yet
    this.bus.on({ type: 'result' }, (msg) => {
      const src = (msg.source || '').toLowerCase();

      // Direct brain results
      if (src.includes('python')) {
        this._codeResults.push(msg);
        const p = this._findPanelByType('code-output');
        if (p) p._addResult(msg);
        this._pulseWorkspaceTab('python-dev');
      }
      if (src.includes('research')) {
        this._researchFindings.push(msg);
        const p = this._findPanelByType('research-results');
        if (p) p._addFinding(msg);
        this._pulseWorkspaceTab('research');
      }

      // Orchestrator aggregated results — extract nested brain results.
      // Handles cases where the direct brain result was missed (WS disconnect).
      if (src.includes('orchestrator') && msg.payload?.results) {
        const results = msg.payload.results;
        for (const [key, val] of Object.entries(results)) {
          if (!val || typeof val !== 'object') continue;
          const data = val.data || val;

          // Python brain result nested in orchestrator response
          if (data.stdout || data.generated_code) {
            const synth = { ...msg, payload: data, source: 'python_brain', _synthetic: true };
            this._codeResults.push(synth);
            const cp = this._findPanelByType('code-output');
            if (cp) cp._addResult(synth);
            this._pulseWorkspaceTab('python-dev');
          }

          // Research brain result nested in orchestrator response
          if (data.summary || data.answer || data.top_sources) {
            const synth = { ...msg, payload: data, source: 'researcher', _synthetic: true };
            this._researchFindings.push(synth);
            const rp = this._findPanelByType('research-results');
            if (rp) rp._addFinding(synth);
            this._pulseWorkspaceTab('research');
          }
        }
      }
    });

    // Load initial workspace
    this.switchWorkspace(workspace);

    this._initialized = true;
    console.log('MorphableUI: initialized');
  }

  /**
   * Switch to a different workspace with FLIP animation.
   *
   * @param {string} workspaceName - Workspace name from WORKSPACE_DEFAULTS
   */
  switchWorkspace(workspaceName) {
    const wsDef = WORKSPACE_DEFAULTS[workspaceName] || WORKSPACE_DEFAULTS.default;

    this.morphThrottle.request(() => {
      try {
      // FIRST: snapshot current positions
      const first = snapshotPanels(this.gridContainer);

      // Unmount current panels
      this._teardownWorkspace();

      // Apply new layout
      this.slotManager.applyLayout(wsDef.layout);

      // Create and mount panels (reuse persistent panels when possible)
      for (const [slotName, panelDef] of Object.entries(wsDef.panels)) {
        const panelId = `${workspaceName}-${slotName}`;
        let panel;

        // Check if we have a persistent instance of this panel type
        if (this._persistentPanels.has(panelDef.type)) {
          panel = this._persistentPanels.get(panelDef.type);
          this._persistentPanels.delete(panelDef.type);
          // Re-attach to grid (subscriptions still active)
          this.gridContainer.appendChild(panel.el);
          // Update grid position
          this.slotManager.assignPanel(slotName, panelId, panel.el);
        } else {
          // Create fresh panel
          panel = createPanel(panelDef.type, panelId, {
            title: panelDef.title,
            icon: panelDef.icon,
          });
          panel.mount(this.gridContainer);
          this.slotManager.assignPanel(slotName, panelId, panel.el);
          panel.subscribe(this.bus);

          // Hydrate result panels from global buffers
          if (panelDef.type === 'code-output' && this._codeResults.length) {
            for (const msg of this._codeResults) panel._addResult(msg);
          }
          if (panelDef.type === 'research-results' && this._researchFindings.length) {
            for (const msg of this._researchFindings) panel._addFinding(msg);
          }
        }

        // Track
        this.panels.set(panelId, panel);
      }

      // Collapse specified slots
      for (const slotName of wsDef.collapsed || []) {
        this.slotManager.collapseSlot(slotName);
        // Update button icon for collapsed panels
        const panelId = this.slotManager.assignments.get(slotName);
        const panel = panelId ? this.panels.get(panelId) : null;
        if (panel) panel._onCollapseToggle();
      }

      // Adapt grid rows for initially collapsed panels
      this._adaptGridForCollapse();

      // LAST + INVERT + PLAY: animate the transition
      flipPanels(this.gridContainer, first, {
        preset: 'panel',
        onComplete: () => {
          console.log(`MorphableUI: workspace "${workspaceName}" loaded`);
        },
      });

      this.currentWorkspace = workspaceName;

      // Update focus state
      this.focusState.workspaces[workspaceName] = {
        state: 'active',
        since: Date.now(),
      };

      // Notify server of workspace change
      this.bus.send({
        type: 'event',
        source: 'morphable_ui',
        target: '*',
        payload: {
          event: 'focus.workspace_changed',
          workspace: workspaceName,
          layout: wsDef.layout,
        },
      });

      // Update workspace selector in UI
      this._updateWorkspaceSelector(workspaceName);

      } catch (e) {
        console.error('[switchWorkspace] ERROR:', e);
        document.getElementById('grid-container').innerHTML =
          `<div style="color:red;padding:20px;font-family:monospace;white-space:pre-wrap">${e.stack || e.message}</div>`;
      }
    });
  }

  /**
   * Show a panel in a specific slot (agent command).
   *
   * @param {string} slotName - Target slot
   * @param {string} panelType - Panel type to create
   * @param {object} [config] - Panel configuration
   */
  showPanel(slotName, panelType, config = {}) {
    this.morphThrottle.request(() => {
      const first = snapshotPanels(this.gridContainer);

      const panelId = `${this.currentWorkspace}-${slotName}`;

      // Remove existing panel in this slot
      const existing = this.panels.get(panelId);
      if (existing) {
        existing.unmount();
        this.panels.delete(panelId);
        this.slotManager.removePanel(panelId);
      }

      // Create new panel
      const panel = createPanel(panelType, panelId, config);
      panel.mount(this.gridContainer);
      this.slotManager.assignPanel(slotName, panelId, panel.el);
      panel.subscribe(this.bus);
      this.panels.set(panelId, panel);

      flipPanels(this.gridContainer, first, { preset: 'panel' });
    });
  }

  /**
   * Hide (collapse) a panel's slot.
   *
   * @param {string} slotName - Slot to collapse
   */
  hidePanel(slotName) {
    this.morphThrottle.request(() => {
      const first = snapshotPanels(this.gridContainer);
      this.slotManager.collapseSlot(slotName);
      // Update button icon
      const panelId = this.slotManager.assignments.get(slotName);
      const panel = panelId ? this.panels.get(panelId) : null;
      if (panel) panel._onCollapseToggle();
      this._adaptGridForCollapse();
      flipPanels(this.gridContainer, first, { preset: 'breathe' });
    });
  }

  /**
   * Expand a collapsed panel's slot.
   *
   * @param {string} slotName - Slot to expand
   */
  expandPanel(slotName) {
    this.morphThrottle.request(() => {
      const first = snapshotPanels(this.gridContainer);
      this.slotManager.expandSlot(slotName);
      // Update button icon
      const panelId = this.slotManager.assignments.get(slotName);
      const panel = panelId ? this.panels.get(panelId) : null;
      if (panel) panel._onCollapseToggle();
      this._adaptGridForCollapse();
      flipPanels(this.gridContainer, first, { preset: 'breathe' });
    });
  }

  /**
   * Create a data pipeline and render its output in a panel.
   *
   * @param {string} pipelineId - Pipeline ID
   * @param {object} definition - Pipeline definition
   * @param {string} slotName - Slot to render in
   */
  createPipeline(pipelineId, definition, slotName) {
    const panelId = `pipeline-${pipelineId}`;

    // Create pipeline panel
    const panel = createPanel('pipeline', panelId, {
      title: definition.title || pipelineId,
      pipeline: definition,
    });

    panel.mount(this.gridContainer);
    this.slotManager.assignPanel(slotName, panelId, panel.el);
    panel.subscribe(this.bus);
    this.panels.set(panelId, panel);

    // Create pipeline and wire to panel
    this.pipelineManager.create(pipelineId, definition, (data) => {
      panel.onPipelineData(data);
    });
  }

  /**
   * Destroy a data pipeline.
   *
   * @param {string} pipelineId
   */
  destroyPipeline(pipelineId) {
    this.pipelineManager.destroy(pipelineId);
    const panelId = `pipeline-${pipelineId}`;
    const panel = this.panels.get(panelId);
    if (panel) {
      panel.unmount();
      this.panels.delete(panelId);
      this.slotManager.removePanel(panelId);
    }
  }

  /**
   * Cleanup on destroy.
   */
  destroy() {
    this._teardownWorkspace();
    this.pipelineManager?.destroyAll();
    this.bus?.disconnect();
    this.morphThrottle?.destroy();
  }

  // ============================================================
  // INTERNAL
  // ============================================================

  _defaultWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}/ws`;
  }

  _teardownWorkspace() {
    // Unmount workspace panels, but PRESERVE persistent panels (chat, task-list, brain-status)
    const statusStrip = this.panels.get('status-strip');
    const PERSISTENT_TYPES = new Set(['chat', 'task-list', 'brain-status']);

    for (const [id, panel] of this.panels) {
      if (id === 'status-strip') continue;
      if (PERSISTENT_TYPES.has(panel.type)) {
        // Detach from DOM but keep alive (subscriptions stay active)
        if (panel.el?.parentNode) panel.el.remove();
        this._persistentPanels.set(panel.type, panel);
        continue;
      }
      panel.unmount();
    }
    this.panels.clear();
    if (statusStrip) this.panels.set('status-strip', statusStrip);

    // Clear pipelines
    this.pipelineManager?.destroyAll();

    // Clear grid
    this.gridContainer.innerHTML = '';
  }

  _initStatusStrip() {
    if (!this.statusStrip) return;

    const strip = new StatusStripPanel('status-strip', {
      title: 'Status',
      icon: '📌',
    });
    strip.mount(this.statusStrip);
    strip.subscribe(this.bus);
    this.panels.set('status-strip', strip);

    // Default status items
    strip.updateItem('connection', {
      icon: '🔴',
      label: 'Bus',
      value: 'Disconnected',
    });
  }

  _sendMessage() {
    const text = this.chatInput.value.trim();
    if (!text) return;

    this.chatInput.value = '';

    // Send to Front Brain via bus
    this.bus.send({
      type: 'task',
      source: 'morphable_ui',
      target: 'front_brain',
      payload: {
        type: 'user_message',
        text,
      },
    });

    // Also add to local chat panel
    const chatPanel = this._findPanelByType('chat');
    if (chatPanel) {
      chatPanel.addMessage({ role: 'user', text });
    }
  }

  _initChatInput() {
    if (!this.chatInput) return;

    this.chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this._sendMessage();
      }
    });

    // Send button
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) {
      sendBtn.addEventListener('click', () => this._sendMessage());
    }
  }

  _onBusConnect() {
    if (this.connectionIndicator) {
      this.connectionIndicator.className = 'connection-connected';
      this.connectionIndicator.title = 'Connected to BigBrain';
    }

    const strip = this.panels.get('status-strip');
    if (strip?.updateItem) {
      strip.updateItem('connection', {
        icon: '🟢',
        label: 'Bus',
        value: 'Connected',
      });
    }

    // Request current focus state
    this.bus.send({
      type: 'query',
      source: 'morphable_ui',
      target: 'front_brain',
      payload: { type: 'focus_state' },
    });
  }

  _onBusDisconnect() {
    if (this.connectionIndicator) {
      this.connectionIndicator.className = 'connection-disconnected';
      this.connectionIndicator.title = 'Disconnected — reconnecting...';
    }
  }

  _handleFocusChange(payload) {
    const event = payload?.event || '';

    if (event === 'focus.workspace_changed') {
      const ws = payload.workspace;
      if (ws && ws !== this.currentWorkspace) {
        this.switchWorkspace(ws);
      }
    } else if (event === 'focus.mode_changed') {
      this.focusState.mode = payload.mode || 'normal';
      document.body.dataset.focusMode = this.focusState.mode;
    }
  }

  _handlePanelCommand(payload) {
    const event = payload?.event || '';
    const slot = payload?.slot;

    if (event === 'ui.panel.show') {
      this.showPanel(slot, payload.type, payload.config);
    } else if (event === 'ui.panel.hide') {
      this.hidePanel(slot);
    } else if (event === 'ui.panel.expand') {
      this.expandPanel(slot);
    } else if (event === 'ui.panel.swap') {
      this.showPanel(slot, payload.type, payload.config);
    }
  }

  _handlePipelineCommand(payload) {
    const event = payload?.event || '';

    if (event === 'ui.pipeline.create') {
      this.createPipeline(payload.id, payload.definition, payload.slot);
    } else if (event === 'ui.pipeline.destroy') {
      this.destroyPipeline(payload.id);
    }
  }

  _findPanelByType(type) {
    for (const panel of this.panels.values()) {
      if (panel.type === type) return panel;
    }
    return null;
  }

  _updateWorkspaceSelector(active) {
    const selector = document.getElementById('workspace-selector');
    if (!selector) return;

    selector.innerHTML = '';
    for (const wsName of Object.keys(WORKSPACE_DEFAULTS)) {
      const meta = WORKSPACE_LABELS[wsName] || { icon: '📁', label: wsName };
      const btn = document.createElement('button');
      btn.className = `ws-btn ${wsName === active ? 'ws-btn-active' : ''}`;
      btn.innerHTML = `<span class="ws-icon">${meta.icon}</span><span class="ws-label">${meta.label}</span>`;
      btn.dataset.workspace = wsName;
      btn.addEventListener('click', () => {
        // Clear notification dot when clicked
        btn.classList.remove('ws-btn-notify');
        this.switchWorkspace(wsName);
      });
      selector.appendChild(btn);
    }
  }

  /** Add a notification dot to a workspace tab to signal results are ready. */
  _pulseWorkspaceTab(wsName) {
    const selector = document.getElementById('workspace-selector');
    if (!selector) return;
    const btn = selector.querySelector(`[data-workspace="${wsName}"]`);
    if (!btn || btn.classList.contains('ws-btn-active')) return;
    btn.classList.add('ws-btn-notify');
  }

  // ============================================================
  // COLLAPSE ↔ GRID ADAPTATION
  //
  // When a panel collapses, the CSS grid row it occupies should
  // shrink to `auto` so the collapsed panel only takes title-bar
  // height.  Rows with expanded panels keep their original `fr`
  // sizing.  Spanning slots (like "primary" in tri-left) don't
  // prevent a row from shrinking — only single-row slots matter.
  // ============================================================

  /**
   * Handle a panel collapse toggle dispatched from panel.js.
   * Wraps the state change in a FLIP animation.
   *
   * @param {string} panelId
   */
  _handleCollapseToggle(panelId) {
    const panel = this.panels.get(panelId);
    if (!panel?.el) return;

    // FIRST: snapshot positions before the change
    const first = snapshotPanels(this.gridContainer);

    // Toggle the collapsed class
    panel.el.classList.toggle('panel-collapsed');
    panel._onCollapseToggle();

    // Also keep SlotManager in sync
    const slot = panel.el.dataset.slot;
    if (slot) {
      if (panel.el.classList.contains('panel-collapsed')) {
        this.slotManager.collapsedSlots.add(slot);
      } else {
        this.slotManager.collapsedSlots.delete(slot);
      }
    }

    // Adapt the CSS grid template
    this._adaptGridForCollapse();

    // FLIP: animate from old to new positions
    flipPanels(this.gridContainer, first, { preset: 'breathe' });
  }

  /**
   * Rebuild the grid template, replacing row sizes with `auto`
   * for rows whose single-row slots are all collapsed.
   */
  _adaptGridForCollapse() {
    const layout = this.slotManager.currentLayout;
    if (!layout) return;

    const template = layout.grid.template;

    // --- Parse grid-template shorthand ---
    // Format: "area names" rowSize "area names" rowSize … / colSizes
    const slashIdx = template.lastIndexOf('/');
    if (slashIdx === -1) return; // malformed, bail

    const rowsPart = template.substring(0, slashIdx).trim();
    const colsPart = template.substring(slashIdx + 1).trim();

    const rowRegex = /"([^"]+)"\s+(\S+)/g;
    const rows = [];
    let m;
    while ((m = rowRegex.exec(rowsPart)) !== null) {
      rows.push({ areas: m[1].trim().split(/\s+/), originalSize: m[2] });
    }

    if (rows.length === 0) return;

    // --- Build slot → set-of-row-indices ---
    const slotRowMap = {};
    rows.forEach((row, idx) => {
      for (const area of row.areas) {
        if (!slotRowMap[area]) slotRowMap[area] = new Set();
        slotRowMap[area].add(idx);
      }
    });

    // --- Determine which slots are currently collapsed ---
    const collapsedSlots = new Set();
    for (const el of this.gridContainer.querySelectorAll('.panel[data-slot]')) {
      if (el.classList.contains('panel-collapsed')) {
        collapsedSlots.add(el.dataset.slot);
      }
    }

    // --- For each row, decide auto vs original size ---
    const newRows = rows.map((row) => {
      const uniqueAreas = [...new Set(row.areas)];

      // Single-row slots: slots that only appear in THIS row
      const singleRowSlots = uniqueAreas.filter(
        (a) => slotRowMap[a] && slotRowMap[a].size === 1
      );

      // No single-row slots in this row → keep original
      if (singleRowSlots.length === 0) return row;

      // All single-row slots collapsed → row becomes auto
      const allCollapsed = singleRowSlots.every((s) => collapsedSlots.has(s));

      return {
        ...row,
        size: allCollapsed ? 'auto' : row.originalSize,
      };
    });

    // --- Rebuild and apply ---
    const rebuilt = newRows
      .map((r) => `"${r.areas.join(' ')}" ${r.size || r.originalSize}`)
      .join(' ');

    this.gridContainer.style.gridTemplate = `${rebuilt} / ${colsPart}`;
  }
}

// ============================================================
// BOOTSTRAP
// ============================================================

let app = null;

function boot() {
  try {
    console.log('[BOOT] Starting MorphableUI...');
    app = new MorphableUI();

    // Determine WebSocket URL
    const wsUrl = document.body.dataset.wsUrl || undefined;
    const workspace = document.body.dataset.workspace || 'default';

    console.log('[BOOT] init() with workspace:', workspace);
    app.init({ wsUrl, workspace });

    // Expose for debugging
    window.__bigbrain = app;
    console.log('[BOOT] Complete');
  } catch (e) {
    console.error('[BOOT] FATAL:', e);
    document.getElementById('grid-container').innerHTML =
      `<div style="color:red;padding:20px;font-family:monospace;white-space:pre-wrap">${e.stack || e.message}</div>`;
  }
}

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}

export { MorphableUI };
