/**
 * morph.js — Spring Physics + FLIP Panel Engine
 *
 * Custom morphing engine for BigBrain's Morphable UI.
 * Zero dependencies. Uses Web Animations API (WAAPI) for GPU-accelerated transitions.
 *
 * Spring math ported from Motion (MIT) — github.com/motiondivision/motion
 * FLIP technique: First-Last-Invert-Play for layout animations.
 *
 * ~400 lines. Full control, zero upstream risk.
 */

// ============================================================
// SPRING PHYSICS
// ============================================================

/**
 * Default spring configuration.
 * Tuned for panel morphing — responsive but not bouncy.
 */
const SPRING_DEFAULTS = {
  stiffness: 100,
  damping: 10,
  mass: 1.0,
  bounce: 0.25,
  restSpeed: 0.01,
  restDelta: 0.001,
};

/**
 * Compute the damping ratio (zeta) for a spring system.
 * ζ < 1: underdamped (bouncy), ζ = 1: critically damped, ζ > 1: overdamped
 */
function dampingRatio(stiffness, damping, mass) {
  return damping / (2 * Math.sqrt(stiffness * mass));
}

/**
 * Create a spring resolver function.
 *
 * Returns a function f(t) => { value, velocity, done }
 * where t is in seconds, value is normalized 0→1.
 *
 * Ported from Motion's spring.ts (MIT license).
 *
 * @param {object} opts - Spring parameters
 * @param {number} opts.stiffness - Spring stiffness (k)
 * @param {number} opts.damping - Damping coefficient (c)
 * @param {number} opts.mass - Mass (m)
 * @param {number} opts.restSpeed - Speed threshold for settling
 * @param {number} opts.restDelta - Position threshold for settling
 * @returns {function} Resolver: (t: number) => { value, velocity, done }
 */
function createSpring(opts = {}) {
  const {
    stiffness = SPRING_DEFAULTS.stiffness,
    damping = SPRING_DEFAULTS.damping,
    mass = SPRING_DEFAULTS.mass,
    restSpeed = SPRING_DEFAULTS.restSpeed,
    restDelta = SPRING_DEFAULTS.restDelta,
  } = opts;

  const w0 = Math.sqrt(stiffness / mass);         // Natural frequency
  const zeta = dampingRatio(stiffness, damping, mass);  // Damping ratio
  const wd = w0 * Math.sqrt(Math.abs(1 - zeta * zeta)); // Damped frequency

  // Initial conditions: moving from 0 to 1
  const x0 = -1; // displacement from target (start=0, target=1, so x0 = 0 - 1 = -1)
  const v0 = 0;  // initial velocity

  let resolver;

  if (zeta < 1) {
    // Underdamped — oscillates, most common for UI springs
    resolver = function (t) {
      const envelope = Math.exp(-zeta * w0 * t);
      const cos = Math.cos(wd * t);
      const sin = Math.sin(wd * t);

      const value =
        1 -
        envelope *
          ((x0 * wd * cos - (v0 + zeta * w0 * x0) * sin) / wd);

      // Derivative for velocity
      const velocity =
        zeta * w0 * envelope *
          ((x0 * wd * cos - (v0 + zeta * w0 * x0) * sin) / wd) -
        envelope *
          ((-x0 * wd * wd * sin - (v0 + zeta * w0 * x0) * wd * cos) / wd);

      return { value, velocity };
    };
  } else if (zeta === 1) {
    // Critically damped — fastest approach without oscillation
    resolver = function (t) {
      const envelope = Math.exp(-w0 * t);
      const value = 1 - envelope * (x0 + (v0 + w0 * x0) * t);
      const velocity =
        envelope * (w0 * x0 + (v0 + w0 * x0) * (w0 * t - 1));

      return { value, velocity };
    };
  } else {
    // Overdamped — slow approach, no oscillation
    const s1 = -w0 * zeta + wd; // wd here is actually real (no i)
    const s2 = -w0 * zeta - wd;
    const A = (x0 * s2 - v0) / (s2 - s1);
    const B = x0 - A;

    resolver = function (t) {
      const e1 = Math.exp(s1 * t);
      const e2 = Math.exp(s2 * t);
      const value = 1 - (A * e1 + B * e2);
      const velocity = -(A * s1 * e1 + B * s2 * e2);

      return { value, velocity };
    };
  }

  // Wrap with done detection
  return function (t) {
    const state = resolver(t);
    const isDone =
      Math.abs(1 - state.value) < restDelta &&
      Math.abs(state.velocity) < restSpeed;

    return {
      value: isDone ? 1 : state.value,
      velocity: state.velocity,
      done: isDone,
    };
  };
}

/**
 * Calculate the duration a spring needs to settle.
 * Steps at 50ms intervals, max 10s.
 *
 * @param {object} opts - Spring parameters
 * @returns {number} Duration in seconds
 */
function calcSpringDuration(opts = {}) {
  const spring = createSpring(opts);
  const step = 0.05; // 50ms steps
  const maxDuration = 10;

  for (let t = step; t <= maxDuration; t += step) {
    const state = spring(t);
    if (state.done) {
      return t;
    }
  }
  return maxDuration;
}

/**
 * Generate a CSS `linear()` easing function from a spring.
 *
 * Samples the spring at regular intervals and produces a CSS string like:
 *   linear(0, 0.12, 0.34, 0.56 50%, 0.78, 0.95, 1.02, 1, 1)
 *
 * Ported from Motion's linear.ts (MIT license).
 *
 * @param {object} opts - Spring parameters
 * @param {number} [resolution=10] - Milliseconds per sample point
 * @returns {string} CSS linear() easing string
 */
function springToLinearCSS(opts = {}, resolution = 10) {
  const spring = createSpring(opts);
  const duration = calcSpringDuration(opts);
  const numPoints = Math.ceil((duration * 1000) / resolution);
  const points = [];

  for (let i = 0; i <= numPoints; i++) {
    const t = (i / numPoints) * duration;
    const { value } = spring(t);
    points.push(Math.round(value * 10000) / 10000);
  }

  // Simplify: remove points that are on a straight line between neighbors
  const simplified = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const expected = simplified[simplified.length - 1] +
      (points[i + 1] - simplified[simplified.length - 1]) *
        (1 / (points.length - i));

    if (Math.abs(points[i] - expected) > 0.005) {
      simplified.push(points[i]);
    }
  }
  simplified.push(points[points.length - 1]);

  return `linear(${simplified.join(', ')})`;
}

// ============================================================
// SPRING PRESETS for common UI transitions
// ============================================================

const SPRING_PRESETS = {
  /** Default panel morph — responsive, slight overshoot */
  panel: { stiffness: 120, damping: 14, mass: 1.0 },

  /** Quick snap — for small element transitions */
  snap: { stiffness: 300, damping: 20, mass: 0.8 },

  /** Gentle ease — for breathing grid proportion changes */
  breathe: { stiffness: 80, damping: 18, mass: 1.2 },

  /** Bouncy — for attention highlights */
  bounce: { stiffness: 200, damping: 10, mass: 1.0 },

  /** Stiff — for status strip expand/collapse */
  stiff: { stiffness: 250, damping: 25, mass: 1.0 },
};

// Pre-compute CSS linear() strings for each preset (avoids runtime recalc)
const _cssCache = {};
function getSpringCSS(presetOrOpts) {
  const key =
    typeof presetOrOpts === 'string'
      ? presetOrOpts
      : JSON.stringify(presetOrOpts);

  if (!_cssCache[key]) {
    const opts =
      typeof presetOrOpts === 'string'
        ? SPRING_PRESETS[presetOrOpts] || SPRING_PRESETS.panel
        : presetOrOpts;
    _cssCache[key] = springToLinearCSS(opts);
  }
  return _cssCache[key];
}

// ============================================================
// FLIP ENGINE
// ============================================================

/**
 * Snapshot the bounding rect of every panel in the grid.
 *
 * @param {HTMLElement} container - Grid container
 * @returns {Map<string, DOMRect>} Panel id → bounding rect
 */
function snapshotPanels(container) {
  const map = new Map();
  for (const panel of container.querySelectorAll('[data-panel-id]')) {
    const id = panel.dataset.panelId;
    map.set(id, panel.getBoundingClientRect());
  }
  return map;
}

/**
 * Execute a FLIP animation on panels after a layout change.
 *
 * Usage:
 *   const first = snapshotPanels(grid);
 *   grid.className = 'layout-focus';   // apply new layout
 *   flipPanels(grid, first, { preset: 'panel' });
 *
 * @param {HTMLElement} container - Grid container
 * @param {Map<string, DOMRect>} firstSnapshot - Positions before layout change
 * @param {object} [options]
 * @param {string} [options.preset='panel'] - Spring preset name
 * @param {object} [options.spring] - Custom spring parameters (overrides preset)
 * @param {function} [options.onComplete] - Called when all animations finish
 * @returns {Animation[]} Array of running WAAPI animations
 */
function flipPanels(container, firstSnapshot, options = {}) {
  const {
    preset = 'panel',
    spring: customSpring,
    onComplete,
  } = options;

  const springOpts = customSpring || SPRING_PRESETS[preset] || SPRING_PRESETS.panel;
  const duration = calcSpringDuration(springOpts) * 1000; // Convert to ms
  const easing = getSpringCSS(springOpts);

  const animations = [];
  const panels = container.querySelectorAll('[data-panel-id]');

  for (const panel of panels) {
    const id = panel.dataset.panelId;
    const first = firstSnapshot.get(id);

    if (!first) {
      // New panel — fade in
      const anim = panel.animate(
        [{ opacity: 0, transform: 'scale(0.95)' }, { opacity: 1, transform: 'scale(1)' }],
        { duration: duration * 0.6, easing, fill: 'none' }
      );
      animations.push(anim);
      continue;
    }

    const last = panel.getBoundingClientRect();

    // Calculate deltas
    const dx = first.left - last.left;
    const dy = first.top - last.top;
    const sw = first.width / (last.width || 1);
    const sh = first.height / (last.height || 1);

    // Skip if nothing changed
    if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5 &&
        Math.abs(sw - 1) < 0.01 && Math.abs(sh - 1) < 0.01) {
      continue;
    }

    // INVERT + PLAY: animate from old position to new
    const anim = panel.animate(
      [
        {
          transform: `translate(${dx}px, ${dy}px) scale(${sw}, ${sh})`,
          transformOrigin: 'top left',
        },
        {
          transform: 'translate(0, 0) scale(1, 1)',
          transformOrigin: 'top left',
        },
      ],
      {
        duration,
        easing,
        fill: 'none',
        composite: 'replace',
      }
    );

    animations.push(anim);
  }

  // Handle removed panels (in firstSnapshot but not in current DOM)
  // We can't animate removed elements, but we could create ghost elements.
  // For now, they simply disappear (CSS transition handles opacity if needed).

  // Fire onComplete when all animations finish
  if (onComplete && animations.length > 0) {
    Promise.all(animations.map((a) => a.finished)).then(onComplete);
  }

  return animations;
}

/**
 * Animate a single panel's proportions (breathing grid).
 * Used for smooth resize without full layout morph.
 *
 * @param {HTMLElement} panel - Panel element
 * @param {object} from - { width, height } or CSS grid values
 * @param {object} to - { width, height } or CSS grid values
 * @param {object} [options]
 * @returns {Animation}
 */
function breathePanel(panel, from, to, options = {}) {
  const { preset = 'breathe', onComplete } = options;
  const springOpts = SPRING_PRESETS[preset] || SPRING_PRESETS.breathe;
  const duration = calcSpringDuration(springOpts) * 1000;
  const easing = getSpringCSS(springOpts);

  const keyframes = [];

  if (from.width !== undefined && to.width !== undefined) {
    keyframes.push(
      { width: from.width, height: from.height || 'auto' },
      { width: to.width, height: to.height || 'auto' }
    );
  } else if (from.gridRow !== undefined) {
    // Grid-based breathing
    keyframes.push(
      { gridRow: from.gridRow, gridColumn: from.gridColumn },
      { gridRow: to.gridRow, gridColumn: to.gridColumn }
    );
  }

  // For grid proportion changes, we use a FLIP approach instead
  // since grid properties aren't directly animatable.
  // Snapshot → change grid → FLIP with size delta.
  const firstRect = panel.getBoundingClientRect();

  // Apply new size
  if (to.flex !== undefined) {
    panel.style.flex = to.flex;
  }

  // Force layout
  panel.offsetHeight; // eslint-disable-line no-unused-expressions

  const lastRect = panel.getBoundingClientRect();
  const sw = firstRect.width / (lastRect.width || 1);
  const sh = firstRect.height / (lastRect.height || 1);

  const anim = panel.animate(
    [
      { transform: `scale(${sw}, ${sh})`, transformOrigin: 'top left' },
      { transform: 'scale(1, 1)', transformOrigin: 'top left' },
    ],
    { duration, easing, fill: 'none' }
  );

  if (onComplete) {
    anim.finished.then(onComplete);
  }

  return anim;
}

/**
 * Highlight a panel with a brief glow/pulse animation.
 *
 * @param {HTMLElement} panel - Panel element to highlight
 * @param {string} [color='var(--accent)'] - Highlight color
 * @returns {Animation}
 */
function highlightPanel(panel, color = 'var(--accent)') {
  return panel.animate(
    [
      { boxShadow: `0 0 0 0 ${color}`, transform: 'scale(1)' },
      { boxShadow: `0 0 20px 4px ${color}`, transform: 'scale(1.005)' },
      { boxShadow: `0 0 0 0 ${color}`, transform: 'scale(1)' },
    ],
    {
      duration: 600,
      easing: getSpringCSS('bounce'),
      fill: 'none',
    }
  );
}

// ============================================================
// RATE LIMITER (anti-seasick)
// ============================================================

/**
 * Rate limiter for layout transitions.
 * Prevents more than one morph per `minInterval` ms.
 * Queues the latest request and fires it when the cooldown expires.
 */
class MorphThrottle {
  constructor(minIntervalMs = 800) {
    this.minInterval = minIntervalMs;
    this._lastMorph = 0;
    this._pending = null;
    this._timer = null;
  }

  /**
   * Request a morph. If within cooldown, queues it.
   * @param {function} morphFn - Function to call to perform the morph
   */
  request(morphFn) {
    const now = Date.now();
    const elapsed = now - this._lastMorph;

    if (elapsed >= this.minInterval) {
      this._execute(morphFn);
    } else {
      // Queue latest (replaces any previous pending)
      this._pending = morphFn;
      if (!this._timer) {
        this._timer = setTimeout(() => {
          this._timer = null;
          if (this._pending) {
            const fn = this._pending;
            this._pending = null;
            this._execute(fn);
          }
        }, this.minInterval - elapsed);
      }
    }
  }

  _execute(fn) {
    this._lastMorph = Date.now();
    fn();
  }

  destroy() {
    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }
    this._pending = null;
  }
}

// ============================================================
// EXPORTS
// ============================================================

export {
  // Spring physics
  createSpring,
  calcSpringDuration,
  springToLinearCSS,
  dampingRatio,
  SPRING_DEFAULTS,
  SPRING_PRESETS,
  getSpringCSS,
  // FLIP engine
  snapshotPanels,
  flipPanels,
  breathePanel,
  highlightPanel,
  // Rate limiter
  MorphThrottle,
};
