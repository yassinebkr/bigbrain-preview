/**
 * layout.js — Layout Catalog + Slot Management
 *
 * Pre-designed grid layouts with named slots.
 * Agent picks a layout; never creates or modifies grids.
 * Spatial stability is the #1 factor (Gajos 2008).
 *
 * Each layout defines:
 *   - CSS grid template
 *   - Named slots (primary, secondary, aux, etc.)
 *   - Slot positions in the grid
 *   - Collapse behavior (how panels shrink to title bars)
 */

// ============================================================
// LAYOUT CATALOG — 7 pre-designed grids
// ============================================================

const LAYOUT_CATALOG = {
  /**
   * Focus: Single panel takes full space.
   * Use: deep work, reading, full-screen preview.
   *
   * ┌──────────────────┐
   * │     primary       │
   * │                   │
   * │                   │
   * └──────────────────┘
   */
  focus: {
    id: 'focus',
    name: 'Focus',
    description: 'Single panel, full viewport',
    grid: {
      template: '"primary" 1fr / 1fr',
    },
    slots: {
      primary: { area: 'primary', defaultVisible: true },
    },
  },

  /**
   * Split: Two equal columns.
   * Use: editor + preview, code + terminal.
   *
   * ┌─────────┬─────────┐
   * │  left   │  right  │
   * │         │         │
   * └─────────┴─────────┘
   */
  split: {
    id: 'split',
    name: 'Split',
    description: 'Two equal columns',
    grid: {
      template: '"left right" 1fr / 1fr 1fr',
      gap: '8px',
    },
    slots: {
      left: { area: 'left', defaultVisible: true },
      right: { area: 'right', defaultVisible: true },
    },
  },

  /**
   * Focus-Left: Wide primary + narrow sidebar.
   * Use: editor + file tree, main + details.
   *
   * ┌────────────┬──────┐
   * │   primary  │ side │
   * │            │      │
   * └────────────┴──────┘
   */
  'focus-left': {
    id: 'focus-left',
    name: 'Focus Left',
    description: 'Wide primary with sidebar',
    grid: {
      template: '"primary side" 1fr / 2fr 1fr',
      gap: '8px',
    },
    slots: {
      primary: { area: 'primary', defaultVisible: true },
      side: { area: 'side', defaultVisible: true },
    },
  },

  /**
   * Tri-Left: Wide primary + two stacked panels on right.
   * Use: editor + terminal + file/outline.
   *
   * ┌────────────┬──────┐
   * │            │ top  │
   * │   primary  ├──────┤
   * │            │ bot  │
   * └────────────┴──────┘
   */
  'tri-left': {
    id: 'tri-left',
    name: 'Tri Left',
    description: 'Primary + two stacked panels',
    grid: {
      template:
        '"primary side-top" 1fr "primary side-bottom" 1fr / 2fr 1fr',
      gap: '8px',
    },
    slots: {
      primary: { area: 'primary', defaultVisible: true },
      'side-top': { area: 'side-top', defaultVisible: true },
      'side-bottom': { area: 'side-bottom', defaultVisible: true },
    },
  },

  /**
   * Quad: Four equal quadrants.
   * Use: dashboard, monitoring, overview mode.
   *
   * ┌─────────┬─────────┐
   * │   tl    │   tr    │
   * ├─────────┼─────────┤
   * │   bl    │   br    │
   * └─────────┴─────────┘
   */
  quad: {
    id: 'quad',
    name: 'Quad',
    description: 'Four equal panels',
    grid: {
      template:
        '"tl tr" 1fr "bl br" 1fr / 1fr 1fr',
      gap: '8px',
    },
    slots: {
      tl: { area: 'tl', defaultVisible: true },
      tr: { area: 'tr', defaultVisible: true },
      bl: { area: 'bl', defaultVisible: true },
      br: { area: 'br', defaultVisible: true },
    },
  },

  /**
   * Primary-Dock: Large primary + bottom dock with 2-3 small panels.
   * Use: main work area + status/tools at bottom.
   *
   * ┌──────────────────┐
   * │     primary       │
   * │                   │
   * ├──────┬─────┬──────┤
   * │ dock1│dock2│dock3 │
   * └──────┴─────┴──────┘
   */
  'primary-dock': {
    id: 'primary-dock',
    name: 'Primary + Dock',
    description: 'Primary with bottom dock panels',
    grid: {
      template:
        '"primary primary primary" 3fr "dock1 dock2 dock3" 1fr / 1fr 1fr 1fr',
      gap: '8px',
    },
    slots: {
      primary: { area: 'primary', defaultVisible: true },
      dock1: { area: 'dock1', defaultVisible: true },
      dock2: { area: 'dock2', defaultVisible: true },
      dock3: { area: 'dock3', defaultVisible: false },
    },
  },

  /**
   * Tri-Bottom: Two columns on top + wide bottom panel.
   * Use: split editor + terminal/output below.
   *
   * ┌─────────┬─────────┐
   * │  left   │  right  │
   * ├─────────┴─────────┤
   * │      bottom       │
   * └──────────────────┘
   */
  'tri-bottom': {
    id: 'tri-bottom',
    name: 'Tri Bottom',
    description: 'Two columns + bottom panel',
    grid: {
      template:
        '"left right" 2fr "bottom bottom" 1fr / 1fr 1fr',
      gap: '8px',
    },
    slots: {
      left: { area: 'left', defaultVisible: true },
      right: { area: 'right', defaultVisible: true },
      bottom: { area: 'bottom', defaultVisible: true },
    },
  },
};

// ============================================================
// SLOT MANAGER
// ============================================================

/**
 * Manages panel-to-slot assignments and layout switching.
 */
class SlotManager {
  /**
   * @param {HTMLElement} container - Grid container element
   */
  constructor(container) {
    this.container = container;
    this.currentLayout = null;
    this.assignments = new Map(); // slotName -> panelId
    this.panelElements = new Map(); // panelId -> HTMLElement
    this.collapsedSlots = new Set(); // Set of collapsed slot names
  }

  /**
   * Apply a layout from the catalog.
   * Does NOT trigger FLIP — caller should snapshot before and flip after.
   *
   * @param {string} layoutId - Layout ID from catalog
   */
  applyLayout(layoutId) {
    const layout = LAYOUT_CATALOG[layoutId];
    if (!layout) {
      console.warn(`Layout "${layoutId}" not found in catalog`);
      return;
    }

    this.currentLayout = layout;

    // Apply CSS grid template
    this.container.style.display = 'grid';
    this.container.style.gridTemplate = layout.grid.template;
    this.container.style.gap = layout.grid.gap || '8px';

    // Update dataset for CSS hooks
    this.container.dataset.layout = layoutId;

    // Position panels in their assigned slots
    this._positionPanels();
  }

  /**
   * Assign a panel to a slot.
   *
   * @param {string} slotName - Slot name from current layout
   * @param {string} panelId - Panel identifier
   * @param {HTMLElement} panelEl - Panel DOM element
   */
  assignPanel(slotName, panelId, panelEl) {
    // Remove panel from any previous slot
    for (const [slot, pid] of this.assignments) {
      if (pid === panelId) {
        this.assignments.delete(slot);
        break;
      }
    }

    this.assignments.set(slotName, panelId);
    this.panelElements.set(panelId, panelEl);
    panelEl.dataset.panelId = panelId;
    panelEl.dataset.slot = slotName;

    // Position if layout is active
    if (this.currentLayout) {
      this._positionPanel(slotName, panelEl);
    }
  }

  /**
   * Remove a panel from its slot.
   *
   * @param {string} panelId - Panel to remove
   */
  removePanel(panelId) {
    for (const [slot, pid] of this.assignments) {
      if (pid === panelId) {
        this.assignments.delete(slot);
        break;
      }
    }
    const el = this.panelElements.get(panelId);
    if (el && el.parentNode) {
      el.remove();
    }
    this.panelElements.delete(panelId);
  }

  /**
   * Collapse a slot to its title bar. Panel stays in grid position.
   *
   * @param {string} slotName - Slot to collapse
   */
  collapseSlot(slotName) {
    this.collapsedSlots.add(slotName);
    const panelId = this.assignments.get(slotName);
    if (panelId) {
      const el = this.panelElements.get(panelId);
      if (el) {
        el.classList.add('panel-collapsed');
      }
    }
  }

  /**
   * Expand a previously collapsed slot.
   *
   * @param {string} slotName - Slot to expand
   */
  expandSlot(slotName) {
    this.collapsedSlots.delete(slotName);
    const panelId = this.assignments.get(slotName);
    if (panelId) {
      const el = this.panelElements.get(panelId);
      if (el) {
        el.classList.remove('panel-collapsed');
      }
    }
  }

  /**
   * Toggle collapse state of a slot.
   *
   * @param {string} slotName
   * @returns {boolean} New collapsed state
   */
  toggleSlot(slotName) {
    if (this.collapsedSlots.has(slotName)) {
      this.expandSlot(slotName);
      return false;
    } else {
      this.collapseSlot(slotName);
      return true;
    }
  }

  /**
   * Check if a slot is collapsed.
   *
   * @param {string} slotName
   * @returns {boolean}
   */
  isCollapsed(slotName) {
    return this.collapsedSlots.has(slotName);
  }

  /**
   * Get the list of available slot names in the current layout.
   *
   * @returns {string[]}
   */
  getSlotNames() {
    if (!this.currentLayout) return [];
    return Object.keys(this.currentLayout.slots);
  }

  /**
   * Get current assignments as a plain object.
   *
   * @returns {object} slotName → panelId
   */
  getAssignments() {
    return Object.fromEntries(this.assignments);
  }

  // ---- Internal ----

  _positionPanels() {
    for (const [slotName, panelId] of this.assignments) {
      const el = this.panelElements.get(panelId);
      if (el) {
        this._positionPanel(slotName, el);
      }
    }
  }

  _positionPanel(slotName, el) {
    if (!this.currentLayout) return;

    const slotDef = this.currentLayout.slots[slotName];
    if (!slotDef) return;

    el.style.gridArea = slotDef.area;

    // Ensure panel is in the container
    if (el.parentNode !== this.container) {
      this.container.appendChild(el);
    }

    // Apply collapsed state
    if (this.collapsedSlots.has(slotName)) {
      el.classList.add('panel-collapsed');
    } else {
      el.classList.remove('panel-collapsed');
    }
  }
}

// ============================================================
// WORKSPACE DEFINITIONS — domain-specific panel + layout configs
// ============================================================

/**
 * Workspace label/icon map for the tab bar.
 */
const WORKSPACE_LABELS = {
  default:       { icon: '🏠', label: 'Home' },
  'python-dev':  { icon: '🐍', label: 'Python' },
  research:      { icon: '🔍', label: 'Research' },
  'web-dev':     { icon: '🌐', label: 'Web' },
  '3d-printing': { icon: '🖨️', label: '3D Print' },
  electronics:   { icon: '⚡', label: 'Electronics' },
};

const WORKSPACE_DEFAULTS = {
  default: {
    layout: 'tri-left',
    panels: {
      primary:       { type: 'chat',         title: 'Chat',         icon: '💬' },
      'side-top':    { type: 'brain-status', title: 'Brains',       icon: '🧠' },
      'side-bottom': { type: 'task-list',    title: 'Tasks',        icon: '📋' },
    },
    collapsed: ['side-bottom'],
  },

  'python-dev': {
    layout: 'tri-left',
    panels: {
      primary:       { type: 'code-output', title: 'Code Output',  icon: '💻' },
      'side-top':    { type: 'chat',        title: 'Chat',         icon: '💬' },
      'side-bottom': { type: 'task-list',   title: 'Tasks',        icon: '📋' },
    },
    collapsed: ['side-bottom'],
  },

  research: {
    layout: 'split',
    panels: {
      left:  { type: 'chat',             title: 'Chat',     icon: '💬' },
      right: { type: 'research-results', title: 'Research', icon: '🔍' },
    },
    collapsed: [],
  },

  'web-dev': {
    layout: 'tri-left',
    panels: {
      primary:       { type: 'chat',        title: 'Chat',    icon: '💬' },
      'side-top':    { type: 'code-output', title: 'Output',  icon: '🌐' },
      'side-bottom': { type: 'task-list',   title: 'Tasks',   icon: '📋' },
    },
    collapsed: ['side-bottom'],
  },

  '3d-printing': {
    layout: 'tri-left',
    panels: {
      primary:       { type: 'chat',        title: 'Chat',           icon: '💬' },
      'side-top':    { type: 'placeholder', title: 'Printer Camera', icon: '📷' },
      'side-bottom': { type: 'task-list',   title: 'Tasks',          icon: '📋' },
    },
    collapsed: ['side-bottom'],
  },

  electronics: {
    layout: 'tri-left',
    panels: {
      primary:       { type: 'chat',        title: 'Chat',      icon: '💬' },
      'side-top':    { type: 'placeholder', title: 'Schematic', icon: '⚡' },
      'side-bottom': { type: 'task-list',   title: 'Tasks',     icon: '📋' },
    },
    collapsed: ['side-bottom'],
  },
};

// ============================================================
// EXPORTS
// ============================================================

export { LAYOUT_CATALOG, SlotManager, WORKSPACE_DEFAULTS, WORKSPACE_LABELS };
