
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

  it('a second task.received replaces the previous run', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('task.received', { task_id: 't2' }));
    expect(useAppStore.getState().activeRun!.id).toBe('t2');
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
    expect(conn.send).toHaveBeenCalledWith('bonjour', [], 'sess-live');
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

  it('sendContractDecision posts the verdict and clears on success', async () => {
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
    });
    expect(useAppStore.getState().contractProposal).toBeNull();
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
