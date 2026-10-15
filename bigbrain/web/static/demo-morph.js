/**
 * demo-morph.js — Replayable morph validation gate (Phase 6.4).
 *
 * Loaded only with ?demo=morph (see index.html loader). Runs a FIXED
 * transition script against the live MorphableUI so every run exercises
 * exactly the same morphs:
 *
 *   default → python-dev → (expand/collapse) → default
 *
 * Validates the three Phase 6 fixes:
 *   1. FLIP identity: persistent panels keep the SAME DOM element across a
 *      workspace switch (morph possible), instead of being recreated.
 *   2. Animations actually play: the moved panel's position changed AND at
 *      least one WAAPI animation ran during the transition.
 *   3. Error isolation: no grid nuke — the grid still holds panels and no
 *      raw stack trace was injected.
 *
 * Results print as a console table and a floating PASS/FAIL overlay.
 */

const STEADY_MS = 1200;   // > morph duration + throttle cooldown
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function panelEl(type) {
  return document.querySelector(`[data-panel-type="${type}"]`);
}

function rectOf(type) {
  const el = panelEl(type);
  return el ? el.getBoundingClientRect() : null;
}

function moved(a, b) {
  if (!a || !b) return false;
  return Math.abs(a.left - b.left) > 4 || Math.abs(a.top - b.top) > 4;
}

function overlay(pass, lines) {
  const box = document.createElement('div');
  box.style.cssText = [
    'position:fixed', 'top:14px', 'left:50%', 'transform:translateX(-50%)',
    'z-index:999', 'padding:12px 18px', 'border-radius:12px',
    'font:12.5px/1.7 ui-monospace,monospace', 'white-space:pre',
    'background:rgba(8,25,39,.94)', 'border:1px solid rgba(62,218,215,.35)',
    'color:#e8f3fa', 'max-width:90vw',
  ].join(';');
  box.textContent = `${pass ? 'PASS' : 'FAIL'}\n${lines.join('\n')}`;
  document.body.appendChild(box);
}

async function runDemo() {
  // Wait for boot.
  for (let i = 0; i < 50 && !window.__bigbrain; i++) await sleep(100);
  const app = window.__bigbrain;
  if (!app) {
    overlay(false, ['window.__bigbrain never appeared (boot failed?)']);
    return;
  }

  const report = [];
  let failures = 0;
  const check = (name, ok, detail = '') => {
    report.push(`${ok ? ' ok ' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`);
    if (!ok) failures++;
  };

  // Count WAAPI animations started during a window of time.
  const originalAnimate = Element.prototype.animate;
  let animationCount = 0;
  Element.prototype.animate = function (...args) {
    animationCount++;
    return originalAnimate.apply(this, args);
  };

  try {
    // --- Step 1: identity across a workspace switch --------------------
    app.switchWorkspace('default');
    await sleep(STEADY_MS);
    const chatBefore = panelEl('chat');
    const tasksBefore = panelEl('task-list');
    const chatRectBefore = rectOf('chat');

    let animationsBefore = animationCount;
    app.switchWorkspace('python-dev');
    await sleep(STEADY_MS);

    const chatAfter = panelEl('chat');
    const chatRectAfter = rectOf('chat');
    const animationsDuringSwitch = animationCount - animationsBefore;

    check('identity: chat panel DOM element survives the switch',
      chatBefore === chatAfter && !!chatAfter,
      chatBefore === chatAfter ? 'same element' : 'element was rebuilt');
    check('identity: task-list DOM element survives the switch',
      panelEl('task-list') === tasksBefore && !!tasksBefore);
    check('morph: chat position changed (primary → side-top)',
      moved(chatRectBefore, chatRectAfter));
    check('morph: WAAPI animations ran during the switch',
      animationsDuringSwitch > 0,
      `${animationsDuringSwitch} animations`);

    // --- Step 2: back to default ----------------------------------------
    animationsBefore = animationCount;
    const chatBeforeBack = panelEl('chat');
    app.switchWorkspace('default');
    await sleep(STEADY_MS);
    check('identity: chat element survives the switch back',
      panelEl('chat') === chatBeforeBack);
    check('morph: WAAPI animations ran on the switch back',
      animationCount - animationsBefore > 0);

    // --- Step 3: collapse/expand within a workspace ---------------------
    const statusPanel = panelEl('brain-status');
    if (statusPanel) {
      animationsBefore = animationCount;
      app.hidePanel('side-top');
      await sleep(STEADY_MS);
      app.expandPanel('side-top');
      await sleep(STEADY_MS);
      check('morph: collapse/expand animated',
        animationCount - animationsBefore > 0);
    }

    // --- Step 4: error isolation ----------------------------------------
    const grid = document.getElementById('grid-container');
    const hasPanels = grid && grid.querySelectorAll('[data-panel-id]').length > 0;
    const hasStackTrace = grid && /<pre|stack|Traceback/i.test(grid.innerHTML);
    check('isolation: grid still holds mounted panels', hasPanels);
    check('isolation: no stack trace injected into the grid', !hasStackTrace);
  } finally {
    Element.prototype.animate = originalAnimate;
  }

  console.log('[morph-demo]', failures === 0 ? 'PASS' : 'FAIL');
  console.table(report.map((r) => ({ result: r })));
  overlay(failures === 0, report);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => setTimeout(runDemo, 300));
} else {
  setTimeout(runDemo, 300);
}
