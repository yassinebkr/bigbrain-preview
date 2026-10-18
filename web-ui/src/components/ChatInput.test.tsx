import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ChatInput } from './ChatInput';
import { useAppStore } from '@/store/appStore';

// Server rendering reads Zustand's initial snapshot by default. Use the
// explicit test snapshot so these tests exercise the actual button states.
vi.mock('@/store/appStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/appStore')>();
  const hook = Object.assign(() => actual.useAppStore.getState(), actual.useAppStore);
  return { ...actual, useAppStore: hook };
});

describe('conversation Stop button', () => {
  it('never shows a stale Stop on the welcome screen', () => {
    useAppStore.setState({ view: 'welcome', activeSessionKey: 'sess-old',
      isStreaming: true, activeRun: { id: 'old', sessionId: 'sess-old',
        status: 'running', startedAt: 1, description: 'old', steps: [], files: [] } });
    expect(renderToStaticMarkup(<ChatInput />)).not.toContain('aria-label="Stop generation"');
  });

  it('shows Stop only for the current conversation run', () => {
    useAppStore.setState({ view: 'chat', activeSessionKey: 'sess-new', isStreaming: false,
      activeRun: { id: 'old', sessionId: 'sess-old', status: 'running',
        startedAt: 1, description: 'old', steps: [], files: [] } });
    expect(renderToStaticMarkup(<ChatInput />)).not.toContain('aria-label="Stop generation"');
    useAppStore.setState({ activeSessionKey: 'sess-old' });
    expect(renderToStaticMarkup(<ChatInput />)).toContain('aria-label="Stop generation"');
  });
});
