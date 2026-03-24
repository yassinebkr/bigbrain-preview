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

import { snapshotPanels, flipPanels, highlightPanel, MorphThrottle, getSpringCSS } from './morph.js';
import { LAYOUT_CATALOG, SlotManager, WORKSPACE_DEFAULTS } from './layout.js';
import { createPanel, registerPanelType, StatusStripPanel } from './panel.js';
import { BusClient } from './bus-client.js';
import { PipelineManager } from './pipeline.js';

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
      // FIRST: snapshot current positions
      const first = snapshotPanels(this.gridContainer);

      // Unmount current panels
      this._teardownWorkspace();

      // Apply new layout
      this.slotManager.applyLayout(wsDef.layout);

      // Create and mount panels
      for (const [slotName, panelDef] of Object.entries(wsDef.panels)) {
        const panelId = `${workspaceName}-${slotName}`;
        const panel = createPanel(panelDef.type, panelId, {
          title: panelDef.title,
          icon: panelDef.icon,
        });

        // Mount into container first (SlotManager will position via grid-area)
        panel.mount(this.gridContainer);

        // Assign to slot
        this.slotManager.assignPanel(slotName, panelId, panel.el);

        // Subscribe to bus
        panel.subscribe(this.bus);

        // Track
        this.panels.set(panelId, panel);
      }

      // Collapse specified slots
      for (const slotName of wsDef.collapsed || []) {
        this.slotManager.collapseSlot(slotName);
      }

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
    // Unmount workspace panels (keep status strip)
    const statusStrip = this.panels.get('status-strip');
    for (const [id, panel] of this.panels) {
      if (id === 'status-strip') continue;
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

    // Status strip is always visible — not part of the workspace grid
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

  _initChatInput() {
    if (!this.chatInput) return;

    this.chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
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
    });
  }

  _onBusConnect() {
    if (this.connectionIndicator) {
      this.connectionIndicator.className = 'connection-connected';
      this.connectionIndicator.title = 'Connected to BigBrain';
    }

    // Update status strip
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
      const btn = document.createElement('button');
      btn.className = `ws-btn ${wsName === active ? 'ws-btn-active' : ''}`;
      btn.textContent = wsName;
      btn.addEventListener('click', () => this.switchWorkspace(wsName));
      selector.appendChild(btn);
    }
  }
}

// ============================================================
// BOOTSTRAP
// ============================================================

let app = null;

function boot() {
  app = new MorphableUI();

  // Determine WebSocket URL
  const wsUrl = document.body.dataset.wsUrl || undefined;
  const workspace = document.body.dataset.workspace || 'default';

  app.init({ wsUrl, workspace });

  // Expose for debugging
  window.__bigbrain = app;
}

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}

export { MorphableUI };
