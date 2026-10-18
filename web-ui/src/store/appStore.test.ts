
  it('contracts.proposal restores a session-scoped active run', () => {
    useAppStore.setState({
      activeRun: null,
      activeSessionKey: 'sess-other',
      runPanelDismissed: true,
    });
    useAppStore.getState().applyRunEvent(ev('contracts.proposal', {
      plan_id: 'plan-approval',
      session_id: 'sess-origin',
      user_request: 'build fitness project',
    }));
    const run = useAppStore.getState().activeRun;
    expect(run?.id).toBe('plan-approval');
    expect(run?.sessionId).toBe('sess-origin');
    expect(run?.awaitingApproval).toBe(true);
    expect(useAppStore.getState().runPanelDismissed).toBe(false);
  });
// Store edge cases — the run state machine (applyRunEvent) and the
// streaming finalize guard. Pure state logic; no React needed.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAppStore } from '@/store/appStore';
import { selectSessionRun } from '@/store/appStore';

beforeEach(() => useAppStore.setState({ sessionRuns: {}, sessionProposals: {}, runsById: {} }));

function reset() {
  useAppStore.setState({
    activeRun: null,
    completedRuns: [],
    activeSessionKey: 'sess-live',
    isStreaming: false,
    streamingText: '',
    messages: [],
    agentActivities: [],
  });
}

const ev = (type: string, detail: any) => ({ type, detail });

describe('multiple independent runs in the same conversation', () => {
  beforeEach(reset);
  it('replaces only obsolete uncorrelated cache entries during restoration', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.routing', { session_id: 'sess-live' }));
    expect(useAppStore.getState().activeRun?.id).toMatch(/^routing-/);
    s.applyRunEvent(ev('task.routing', { task_id: 'restored-web', session_id: 'sess-live' }));
    expect(Object.keys(useAppStore.getState().runsById)).toEqual(['restored-web']);
  });

  it('does not lose a user message sent while history was loading', () => {
    useAppStore.setState({ messages: [{ id: 'local', role: 'user', content: 'New message', timestamp: 3000 }] });
    useAppStore.getState().restoreSessionHistory('sess-live', [
      { id: 'old', role: 'assistant', content: 'Previous response', timestamp: 1000 },
    ], 2000);
    expect(useAppStore.getState().messages.map((m) => m.content)).toEqual(['Previous response', 'New message']);
    useAppStore.getState().restoreSessionHistory('sess-other', [], 4000);
    expect(useAppStore.getState().messages).toHaveLength(2);
  });

  it('a quick taskboard action cannot replace or finish an ongoing web project', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.routing', { task_id: 'web', session_id: 'sess-live', description: 'Running app' }));
    s.applyRunEvent(ev('task.received', { task_id: 'web', session_id: 'sess-live' }));
    s.applyRunEvent(ev('subtask.started', { task_id: 'web', subtask_id: 'web-file', brain: 'web_app_brain_0' }));
    s.applyRunEvent(ev('task.routing', { task_id: 'board', session_id: 'sess-live', description: 'Laundry' }));
    s.applyRunEvent(ev('task.received', { task_id: 'board', session_id: 'sess-live' }));
    expect(useAppStore.getState().activeRun?.id).toBe('web');
    expect(Object.keys(useAppStore.getState().runsById)).toEqual(['web', 'board']);
    s.applyRunEvent(ev('task.complete', { task_id: 'board', session_id: 'sess-live', result_kind: 'taskboard' }));
    expect(useAppStore.getState().activeRun?.id).toBe('web');
    expect(useAppStore.getState().completedRuns[0].resultKind).toBe('taskboard');
    s.applyRunEvent(ev('task.progress', { task_id: 'web', subtask_id: 'web-file', stage: 'browser_testing' }));
    expect(useAppStore.getState().activeRun?.steps[0].description).toBe('Tests navigateur');
    s.applyRunEvent(ev('task.complete', { task_id: 'web', session_id: 'sess-live', project_path: 'sandbox/running', entry_point: 'index.html' }));
    expect(useAppStore.getState().completedRuns).toHaveLength(2);
    expect(useAppStore.getState().activeRun).toBeNull();
    expect(useAppStore.getState().runsById).toEqual({});
    // Snapshot/reconnect cannot resurrect either completed run.
    s.applyRunEvent(ev('task.routing', { task_id: 'web', session_id: 'sess-live' }));
    s.applyRunEvent(ev('task.complete', { task_id: 'web', session_id: 'sess-live' }));
    expect(useAppStore.getState().runsById).toEqual({});
    expect(useAppStore.getState().completedRuns).toHaveLength(2);
  });

  it('switches visible activities without losing either and cancels only this conversation', () => {
    const s = useAppStore.getState();
    for (const task_id of ['web', 'board']) s.applyRunEvent(ev('task.received', { task_id, session_id: 'sess-live' }));
    s.applyRunEvent(ev('task.received', { task_id: 'other', session_id: 'sess-other' }));
    s.selectRun('board');
    expect(useAppStore.getState().activeRun?.id).toBe('board');
    s.stopGeneration();
    expect(Object.keys(useAppStore.getState().runsById)).toEqual(['other']);
    expect(useAppStore.getState().completedRuns).toHaveLength(2);
  });
});

describe('applyRunEvent — run state machine', () => {
  beforeEach(reset);

  it('task.received opens a run', () => {
    useAppStore.getState().applyRunEvent(
      ev('task.received', { task_id: 't1', description: 'make hello.py', subtasks_count: 2 }));
    const run = useAppStore.getState().activeRun!;
    expect(run.id).toBe('t1');
    expect(run.status).toBe('running');
    expect(run.description).toBe('make hello.py');
  });

  it('events without an active run are ignored', () => {
    useAppStore.getState().applyRunEvent(
      ev('subtask.complete', { task_id: 't1', subtask_id: 's1' }));
    expect(useAppStore.getState().activeRun).toBeNull();
  });

  it('subtask.started upserts a running step; complete updates it with duration', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('subtask.started', {
      task_id: 't1', subtask_id: 's1', brain: 'python_brain', description: 'write hello.py',
    }));
    s.applyRunEvent(ev('subtask.started', {
      task_id: 't1', subtask_id: 's1', brain: 'python_brain', description: 'write hello.py (redispatch)',
    }));
    let run = useAppStore.getState().activeRun!;
    expect(run.steps).toHaveLength(1); // upsert, not append
    expect(run.steps[0].status).toBe('running');
    expect(run.awaitingApproval).toBe(false);

    s.applyRunEvent(ev('subtask.complete', {
      task_id: 't1', subtask_id: 's1', execution_time: 1.5,
    }));
    run = useAppStore.getState().activeRun!;
    expect(run.steps[0].status).toBe('done');
    expect(run.steps[0].durationMs).toBe(1500);
  });

  it('subtask.complete for an unknown step adds a minimal step (missed started)', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('subtask.failed', { task_id: 't1', subtask_id: 'ghost' }));
    const run = useAppStore.getState().activeRun!;
    expect(run.steps).toHaveLength(1);
    expect(run.steps[0].status).toBe('failed');
  });

  it('workspace.file_written appends and dedupes paths', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('workspace.file_written', { path: 'sandbox/hello.py' }));
    s.applyRunEvent(ev('workspace.file_written', { path: 'sandbox/hello.py' }));
    s.applyRunEvent(ev('workspace.file_written', { path: 'sandbox/notes.md' }));
    const run = useAppStore.getState().activeRun!;
    expect(run.files.map((f) => f.path)).toEqual(['sandbox/hello.py', 'sandbox/notes.md']);
  });

  it('null detail never crashes the machine', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', undefined));
    s.applyRunEvent(ev('subtask.started', undefined));
    s.applyRunEvent(ev('workspace.file_written', undefined));
    const run = useAppStore.getState().activeRun!;
    expect(run.status).toBe('running');
  });

  it('task.complete / failed / cancelled dock the run in its conversation', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('task.complete', { task_id: 't1' }));
    expect(useAppStore.getState().activeRun).toBeNull();
    expect(useAppStore.getState().completedRuns.at(-1)?.status).toBe('done');
    expect(useAppStore.getState().completedRuns.at(-1)?.sessionId).toBe('sess-live');

    useAppStore.setState({ activeRun: null });
    const s2 = useAppStore.getState();
    s2.applyRunEvent(ev('task.received', { task_id: 't2' }));
    s2.applyRunEvent(ev('task.failed', { task_id: 't2', error: 'boom' }));
    expect(useAppStore.getState().completedRuns.at(-1)?.status).toBe('failed');
    expect(useAppStore.getState().completedRuns.at(-1)?.error).toBe('boom');

    useAppStore.setState({ activeRun: null });
    const s3 = useAppStore.getState();
    s3.applyRunEvent(ev('task.received', { task_id: 't3' }));
    s3.applyRunEvent(ev('task.cancelled', { task_id: 't3' }));
    expect(useAppStore.getState().completedRuns.at(-1)?.status).toBe('cancelled');
  });

  it('a second task.received preserves both runs and the selected one', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('task.received', { task_id: 't2' }));
    expect(useAppStore.getState().activeRun!.id).toBe('t1');
    expect(Object.keys(useAppStore.getState().runsById)).toEqual(['t1', 't2']);
  });

  it('verification.run_recorded attaches the gate verdict to the run', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('verification.run_recorded', {
      run_id: 'run-abc', verdict: 'passed', attempt: 1,
      stages: [
        { name: 'syntax', status: 'passed' },
        { name: 'compile', status: 'passed' },
        { name: 'run', status: 'passed' },
        { name: 'contracts', status: 'passed' },
        { name: 'tests', status: 'not_applicable' },
      ],
    }));
    const run = useAppStore.getState().activeRun!;
    expect(run.verification).toBeDefined();
    expect(run.verification!.verdict).toBe('passed');
    expect(run.verification!.runId).toBe('run-abc');
    expect(run.verification!.stages).toHaveLength(5);
    expect(run.verification!.stages[4].status).toBe('not_applicable');
  });

  it('orphan verification events are dropped (no active run)', () => {
    useAppStore.getState().applyRunEvent(
      ev('verification.run_recorded', { run_id: 'r', verdict: 'passed' }));
    expect(useAppStore.getState().activeRun).toBeNull();
  });

  it('unknown verdicts collapse to inconclusive; bad stages shapes survive', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('verification.run_recorded', {
      run_id: 'r2', verdict: 'something-else', stages: 'not-an-array',
    }));
    const run = useAppStore.getState().activeRun!;
    expect(run.verification!.verdict).toBe('inconclusive');
    expect(run.verification!.stages).toEqual([]);
  });
});

describe('finalizeStreaming — empty buffer guard', () => {
  beforeEach(reset);

  it('empty buffer produces no blank bubble', () => {
    useAppStore.setState({ isStreaming: true, streamingText: '', messages: [] });
    useAppStore.getState().finalizeStreaming();
    const s = useAppStore.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.messages).toHaveLength(0);
  });

  it('whitespace-only buffer produces no blank bubble', () => {
    useAppStore.setState({ isStreaming: true, streamingText: '  \n  ', messages: [] });
    useAppStore.getState().finalizeStreaming();
    expect(useAppStore.getState().messages).toHaveLength(0);
  });

  it('real text becomes an assistant message', () => {
    useAppStore.setState({ isStreaming: true, streamingText: 'hello there', messages: [] });
    useAppStore.getState().finalizeStreaming();
    const s = useAppStore.getState();
    expect(s.messages).toHaveLength(1);
    expect(s.messages[0].role).toBe('assistant');
    expect(s.messages[0].content).toBe('hello there');
  });
});

// ── Sessions (real server-side conversations) ────────────────────────────

function mockConnection(overrides: Record<string, any> = {}) {
  return {
    send: vi.fn(),
    cancel: vi.fn(),
    switchSession: vi.fn(),
    loadHistory: vi.fn(),
    listSessions: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    ...overrides,
  };
}

describe('sessions', () => {
  it('home navigation creates a new session without inheriting the failed run', () => {
    const conn = mockConnection({
      createSession: vi.fn((cb) => cb({ id: 'sess-fresh' })),
    });
    useAppStore.setState({ connection: conn as any, activeSessionKey: 'sess-touch',
      view: 'chat', isStreaming: true, streamingText: 'old',
      messages: [{ id: 'old', role: 'user', content: 'TouchDesigner', timestamp: 1 }],
      completedRuns: [{ id: 'touch', sessionId: 'sess-touch', status: 'failed',
        description: 'TouchDesigner', startedAt: 1, finishedAt: 2, files: [], steps: [] }],
    });
    useAppStore.getState().setView('welcome');
    const s = useAppStore.getState();
    expect(s.activeSessionKey).toBe('sess-fresh');
    expect(s.isStreaming).toBe(false);
    expect(s.streamingText).toBe('');
    expect(s.messages).toEqual([]);
    expect(s.completedRuns.filter((r) => r.sessionId === s.activeSessionKey)).toEqual([]);
    expect(s.completedRuns[0].sessionId).toBe('sess-touch');
  });

  it('first send waits for session creation and keeps the first message visible', async () => {
    let created!: (session: any) => void;
    const conn = mockConnection({ createSession: vi.fn((cb) => { created = cb; }) });
    useAppStore.setState({ connection: conn as any });
    useAppStore.getState().startNewSession();
    useAppStore.getState().setInputText('new React project');
    useAppStore.getState().sendMessage();
    expect(conn.send).not.toHaveBeenCalled();
    created({ id: 'sess-delayed' });
    await Promise.resolve();
    expect(conn.send).toHaveBeenCalledWith('new React project', [], 'sess-delayed', null);
    expect(useAppStore.getState().messages[0].content).toBe('new React project');
    expect(useAppStore.getState().view).toBe('chat');
  });

  it('late session creation cannot replace a conversation opened meanwhile', () => {
    let created!: (session: any) => void;
    const conn = mockConnection({ createSession: vi.fn((cb) => { created = cb; }) });
    useAppStore.setState({ connection: conn as any });
    useAppStore.getState().startNewSession();
    useAppStore.getState().openSession('sess-opened');
    created({ id: 'sess-late' });
    expect(useAppStore.getState().activeSessionKey).toBe('sess-opened');
  });

  it('late history cannot replace the visible conversation', () => {
    let loaded!: (frame: any) => void;
    const conn = mockConnection({ loadHistory: vi.fn((cb) => { loaded = cb; }) });
    useAppStore.setState({ connection: conn as any });
    useAppStore.getState().openSession('sess-old');
    useAppStore.getState().startNewSession();
    loaded({ ok: true, payload: { messages: [{ content: 'old history' }] } });
    expect(useAppStore.getState().messages).toEqual([]);
    expect(useAppStore.getState().view).toBe('welcome');
  });

  beforeEach(() => {
    reset();
    useAppStore.setState({ sessions: [], activeSessionKey: '' });
  });

  it('refreshSessions maps server sessions into the store', () => {
    const conn = mockConnection({
      listSessions: vi.fn((cb) => cb([
        { id: 'sess-a', title: 'blague.py', updated_at: 100, message_count: 4 },
        { id: 'sess-b', title: 'New conversation', updated_at: 50, message_count: 0 },
      ])),
    });
    useAppStore.setState({ connection: conn as any });
    useAppStore.getState().refreshSessions();
    const sessions = useAppStore.getState().sessions;
    expect(sessions).toHaveLength(2);
    expect(sessions[0]).toEqual({
      key: 'sess-a', title: 'blague.py', timestamp: 100000, messageCount: 4,
    });
  });

  it('startNewSession creates a server session and resets the view', () => {
    const conn = mockConnection({
      createSession: vi.fn((cb) => cb({ id: 'sess-new', title: 'New conversation' })),
      listSessions: vi.fn((cb) => cb([{ id: 'sess-new', title: 'New conversation', updated_at: 1, message_count: 0 }])),
    });
    useAppStore.setState({ connection: conn as any, messages: [
      { id: 'm1', role: 'user', content: 'old', timestamp: 1 },
    ] });
    useAppStore.getState().startNewSession();
    const s = useAppStore.getState();
    expect(s.activeSessionKey).toBe('sess-new');
    expect(s.messages).toHaveLength(0);
    expect(s.view).toBe('welcome');
    expect(conn.createSession).toHaveBeenCalled();
  });

  it('startNewSession offline clears locally without a fake id', () => {
    const conn = mockConnection();
    delete (conn as any).createSession;
    useAppStore.setState({ connection: conn as any, messages: [
      { id: 'm1', role: 'user', content: 'old', timestamp: 1 },
    ] });
    useAppStore.getState().startNewSession();
    const s = useAppStore.getState();
    expect(s.activeSessionKey).toBe('');
    expect(s.messages).toHaveLength(0);
  });

  it('openSession loads the history from the server', () => {
    const conn = mockConnection({
      loadHistory: vi.fn((cb, sessionId) => {
        expect(sessionId).toBe('sess-x');
        cb({ ok: true, payload: { messages: [
          { id: 'h1', role: 'user', content: 'question', timestamp: 1000 },
          { id: 'h2', role: 'assistant', content: 'réponse', timestamp: 2000 },
        ] } });
      }),
    });
    useAppStore.setState({ connection: conn as any });
    useAppStore.getState().openSession('sess-x');
    const s = useAppStore.getState();
    expect(s.activeSessionKey).toBe('sess-x');
    expect(s.messages).toHaveLength(2);
    expect(s.messages[1].content).toBe('réponse');
    expect(s.view).toBe('chat');
    expect(s.sidebarPanel).toBeNull();
  });

  it('sendMessage carries the active session id', () => {
    const conn = mockConnection();
    useAppStore.setState({
      connection: conn as any,
      activeSessionKey: 'sess-live',
      inputText: 'bonjour',
    });
    useAppStore.getState().sendMessage();
    expect(conn.send).toHaveBeenCalledWith('bonjour', [], 'sess-live', null);
  });
});

describe('contract approval (Phase B)', () => {
  beforeEach(() => {
    useAppStore.setState({ contractProposal: null, contractSending: false });
  });

  it('setContractProposal stores and clears the pending proposal', () => {
    useAppStore.getState().setContractProposal({
      designId: 'task-abc',
      planId: 'p1',
      request: 'écris fibonacci.py',
      contracts: ['fibonacci.py existe'],
    });
    expect(useAppStore.getState().contractProposal?.designId).toBe('task-abc');
    useAppStore.getState().setContractProposal(null);
    expect(useAppStore.getState().contractProposal).toBeNull();
  });

  it('HTTP acknowledgement does not resolve the contract before a recorded verdict', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    useAppStore.getState().setContractProposal({
      designId: 'task-abc', planId: 'p1', request: 'x', contracts: ['c'],
    });
    await useAppStore.getState().sendContractDecision(true);
    expect(fetchMock).toHaveBeenCalledWith('/api/contracts/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ design_id: 'task-abc', plan_id: 'p1', approve: true }),
      signal: expect.any(AbortSignal),
    });
    expect(useAppStore.getState().contractProposal?.planId).toBe('p1');
    vi.unstubAllGlobals();
  });

  it('sendContractDecision keeps the card on failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false });
    vi.stubGlobal('fetch', fetchMock);
    useAppStore.getState().setContractProposal({
      designId: 'task-abc', planId: 'p1', request: 'x', contracts: ['c'],
    });
    await useAppStore.getState().sendContractDecision(false);
    expect(useAppStore.getState().contractProposal).not.toBeNull();
    expect(useAppStore.getState().contractSending).toBe(false);
    vi.unstubAllGlobals();
  });

  it('an old HTTP decision cannot modify a newer proposal', async () => {
    let finish!: (value: any) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { finish = resolve; })));
    useAppStore.getState().setContractProposal({ designId: 'old', planId: 'old', request: 'old', contracts: ['c'] });
    const decision = useAppStore.getState().sendContractDecision(true);
    useAppStore.getState().setContractProposal({ designId: 'new', planId: 'new', request: 'new', contracts: ['c'] });
    finish({ ok: false });
    await decision;
    expect(useAppStore.getState().contractProposal?.planId).toBe('new');
    expect(useAppStore.getState().contractError).toBeNull();
    vi.unstubAllGlobals();
  });
});

describe('dismissNudge', () => {
  it('records a dismissal without duplicates and stays bounded', () => {
    useAppStore.setState({ dismissedNudges: [] });
    useAppStore.getState().dismissNudge('k1');
    useAppStore.getState().dismissNudge('k1');
    useAppStore.getState().dismissNudge('k2');
    expect(useAppStore.getState().dismissedNudges).toEqual(['k1', 'k2']);
  });
});

describe('runPanelDismissed — new run reopens the panel', () => {
  it('task.received resets the dismissal', () => {
    useAppStore.setState({ activeRun: null, runPanelDismissed: true });
    useAppStore.getState().applyRunEvent(
      ev('task.received', { task_id: 't9', description: 'nouveau run' }));
    expect(useAppStore.getState().activeRun?.id).toBe('t9');
    expect(useAppStore.getState().runPanelDismissed).toBe(false);
  });
});

describe('applyFsRunEvent — streaming manual runs', () => {
  beforeEach(() => {
    useAppStore.setState({ liveRuns: {} });
  });

  it('accumulates output deltas per stream then finalises', () => {
    const s = useAppStore.getState();
    s.applyFsRunEvent(ev('fs.run_output', { runId: 'r1', stream: 'out', delta: 'hello\n' }));
    s.applyFsRunEvent(ev('fs.run_output', { runId: 'r1', stream: 'err', delta: 'warn\n' }));
    s.applyFsRunEvent(ev('fs.run_output', { runId: 'r1', stream: 'out', delta: 'world\n' }));
    let run = useAppStore.getState().liveRuns.r1;
    expect(run.out).toBe('hello\nworld\n');
    expect(run.err).toBe('warn\n');
    expect(run.done).toBe(false);

    s.applyFsRunEvent(ev('fs.run_result', {
      runId: 'r1', ok: true, exitCode: 0,
      stdout: 'hello\nworld\n', stderr: '', durationMs: 5, timedOut: false,
    }));
    run = useAppStore.getState().liveRuns.r1;
    expect(run.done).toBe(true);
    expect(run.result.ok).toBe(true);
    expect(run.result.runId).toBeUndefined(); // the id is not part of the result
  });

  it('ignores events without a runId', () => {
    useAppStore.getState().applyFsRunEvent(ev('fs.run_output', { delta: 'orphan' }));
    expect(useAppStore.getState().liveRuns).toEqual({});
  });
});

describe('run record is scoped to its conversation', () => {
  it('preparation progress is timed, kept through task.received and scoped to its session', () => {
    useAppStore.setState({ activeSessionKey: 'sess-progress', activeRun: null });
    useAppStore.getState().applyRunEvent(ev('task.routing', { session_id: 'sess-progress' }));
    useAppStore.getState().applyRunEvent(ev('planning.stage', {
      session_id: 'sess-progress', stage: 'assessment', status: 'done',
      description: 'Analyse de la demande', elapsed_ms: 1240,
    }));
    useAppStore.getState().applyRunEvent(ev('planning.stage', {
      session_id: 'sess-other', stage: 'architect', status: 'running', description: 'Foreign',
    }));
    expect(useAppStore.getState().activeRun?.steps).toHaveLength(1);
    useAppStore.getState().applyRunEvent(ev('task.received', { task_id: 'p', session_id: 'sess-progress' }));
    expect(useAppStore.getState().activeRun?.steps[0]).toMatchObject({
      id: 'planning-assessment', status: 'done', durationMs: 1240,
    });
  });
  it('a late terminal event from another run cannot dock the current run', () => {
    useAppStore.setState({ activeRun: {
      id: 'new-plan', sessionId: 'sess-new', status: 'running',
      description: 'new project', startedAt: 1, files: [], steps: [],
    }, completedRuns: [] });
    useAppStore.getState().applyRunEvent(ev('task.failed', {
      task_id: 'old-plan', session_id: 'sess-old', error: 'old failure',
    }));
    expect(useAppStore.getState().activeRun?.id).toBe('new-plan');
    expect(useAppStore.getState().completedRuns).toEqual([]);
  });
  it('opening another session preserves the originating run', () => {
    useAppStore.setState({
      activeSessionKey: 'sess-origin',
      activeRun: { sessionId: 'sess-origin', id: 'old', description: 'old run', status: 'running',
                   startedAt: 1, steps: [], files: [] },
      runPanelDismissed: true,
    });
    useAppStore.getState().openSession('sess-other');
    expect(useAppStore.getState().activeRun?.sessionId).toBe('sess-origin');
    expect(useAppStore.getState().activeSessionKey).toBe('sess-other');
    expect(useAppStore.getState().runPanelDismissed).toBe(false);
  });

  it('task.routing immediately opens a run for the named session', () => {
    useAppStore.getState().applyRunEvent(
      ev('task.routing', { session_id: 'sess-origin', description: 'préparation' }));
    expect(useAppStore.getState().activeRun?.sessionId).toBe('sess-origin');
    expect(useAppStore.getState().activeRun?.description).toBe('préparation');
  });
});

describe('applyRunEvent — execution.output streaming', () => {
  beforeEach(() => {
    useAppStore.setState({ activeRun: null, isStreaming: false });
  });

  it('attaches streamed deltas to the matching running step', () => {
    useAppStore.getState().applyRunEvent(
      ev('task.received', { task_id: 't1', description: 'project' }));
    useAppStore.getState().applyRunEvent(
      ev('subtask.started', { task_id: 't1', subtask_id: 's1', brain: 'python_brain_0', description: 'write a.py' }));

    useAppStore.getState().applyRunEvent(
      ev('execution.output', { brain: 'python_brain_0', subtask_id: 's1', stream: 'out', delta: 'compiling…\n' }));
    useAppStore.getState().applyRunEvent(
      ev('execution.output', { brain: 'python_brain_0', subtask_id: 's1', stream: 'out', delta: 'done\n' }));

    const run = useAppStore.getState().activeRun!;
    expect(run.steps[0].liveOutput).toBe('compiling…\ndone\n');
  });

  it('ignores output when no run is active', () => {
    useAppStore.getState().applyRunEvent(
      ev('execution.output', { delta: 'orphan' }));
    expect(useAppStore.getState().activeRun).toBeNull();
  });
});

it('keeps project launch metadata for a single-file modification', () => {
  useAppStore.setState({ activeRun: null });
  useAppStore.getState().applyRunEvent(
    ev('task.received', { task_id: 'edit-1', description: 'edit programme.py' }));
  useAppStore.getState().applyRunEvent(ev('task.complete', {
    task_id: 'edit-1', project_name: 'fitness',
    project_path: 'sandbox/fitness', entry_point: 'index.html', runnable: true,
    deliverable_type: 'web_app', preview_url: 'http://127.0.0.1:3200',
  }));
  expect(useAppStore.getState().completedRuns.at(-1)).toMatchObject({
    projectName: 'fitness', projectPath: 'sandbox/fitness',
    entryPoint: 'index.html', deliverableType: 'web_app',
    previewUrl: 'http://127.0.0.1:3200', runnable: true,
  });
});

it('Stop docks the active run as cancelled and removes its approval controls', () => {
  useAppStore.setState({ activeRun: null, completedRuns: [], connection: null, activeSessionKey: 'stop-session' });
  useAppStore.getState().applyRunEvent(ev('task.received', {
    task_id: 'stopped-run', session_id: 'stop-session',
  }));
  useAppStore.getState().stopGeneration();
  expect(useAppStore.getState().activeRun).toBeNull();
  expect(useAppStore.getState().completedRuns.at(-1)).toMatchObject({
    id: 'stopped-run', status: 'cancelled', sessionId: 'stop-session',
  });
  expect(useAppStore.getState().contractProposal).toBeNull();
});

describe('concurrent runs and approvals', () => {
  it('finishing A preserves the live run and pending approval of B', () => {
    useAppStore.setState({ activeRun: null, completedRuns: [], connection: null, activeSessionKey: 'A' });
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 'pA', session_id: 'A' }));
    s.applyRunEvent(ev('contracts.proposal', { plan_id: 'pA', design_id: 'dA', session_id: 'A', contracts: ['A'] }));
    s.openSession('B');
    s.applyRunEvent(ev('task.received', { task_id: 'pB', session_id: 'B' }));
    s.applyRunEvent(ev('contracts.proposal', { plan_id: 'pB', design_id: 'dB', session_id: 'B', contracts: ['B'] }));
    s.applyRunEvent(ev('subtask.started', { task_id: 'pA', subtask_id: 'sA' }));
    expect(useAppStore.getState().sessionRuns.A.steps[0].id).toBe('sA');
    expect(useAppStore.getState().sessionRuns.B.steps).toEqual([]);
    s.applyRunEvent(ev('task.complete', { task_id: 'pA', session_id: 'A' }));
    expect(selectSessionRun(useAppStore.getState())?.id).toBe('pB');
    expect(useAppStore.getState().contractProposal?.planId).toBe('pB');
    expect(useAppStore.getState().sessionProposals.A).toBeUndefined();
    expect(useAppStore.getState().completedRuns.at(-1)?.sessionId).toBe('A');
    s.openSession('A');
    expect(selectSessionRun(useAppStore.getState())).toBeNull();
    s.openSession('B');
    expect(selectSessionRun(useAppStore.getState())?.id).toBe('pB');
    expect(useAppStore.getState().contractProposal?.planId).toBe('pB');
  });

  it('Stop while a session is being created prevents the delayed send', async () => {
    let created!: (session: any) => void;
    const conn = mockConnection({ createSession: vi.fn((cb) => { created = cb; }) });
    useAppStore.setState({ connection: conn as any });
    useAppStore.getState().startNewSession();
    useAppStore.getState().setInputText('Do not send after Stop');
    useAppStore.getState().sendMessage();
    useAppStore.getState().stopGeneration();
    created({ id: 'sess-created-late' });
    await Promise.resolve();
    expect(conn.send).not.toHaveBeenCalled();
    expect(useAppStore.getState().isStreaming).toBe(false);
  });
});
