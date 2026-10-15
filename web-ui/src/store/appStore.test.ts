// Store edge cases — the run state machine (applyRunEvent) and the
// streaming finalize guard. Pure state logic; no React needed.

import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from '@/store/appStore';

function reset() {
  useAppStore.setState({
    activeRun: null,
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

  it('task.complete / failed / cancelled close the run', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('task.complete', { task_id: 't1' }));
    expect(useAppStore.getState().activeRun!.status).toBe('done');

    useAppStore.setState({ activeRun: null });
    const s2 = useAppStore.getState();
    s2.applyRunEvent(ev('task.received', { task_id: 't2' }));
    s2.applyRunEvent(ev('task.failed', { task_id: 't2', error: 'boom' }));
    expect(useAppStore.getState().activeRun!.status).toBe('failed');
    expect(useAppStore.getState().activeRun!.error).toBe('boom');

    useAppStore.setState({ activeRun: null });
    const s3 = useAppStore.getState();
    s3.applyRunEvent(ev('task.received', { task_id: 't3' }));
    s3.applyRunEvent(ev('task.cancelled', { task_id: 't3' }));
    expect(useAppStore.getState().activeRun!.status).toBe('cancelled');
  });

  it('a second task.received replaces the previous run', () => {
    const s = useAppStore.getState();
    s.applyRunEvent(ev('task.received', { task_id: 't1' }));
    s.applyRunEvent(ev('task.received', { task_id: 't2' }));
    expect(useAppStore.getState().activeRun!.id).toBe('t2');
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
