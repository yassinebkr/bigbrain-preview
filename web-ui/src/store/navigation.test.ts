/** Back navigation preserves the active chat while unwinding views and panels. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAppStore } from './appStore';
import { useWorkspaceStore } from './workspaceStore';

beforeEach(() => {
  useAppStore.setState({ view:'chat', activeSessionKey:'session-a', navigationHistory:[],
    sidebarPanel:null, settingsSection:'general', connection:null });
  useWorkspaceStore.setState({ sessions:{} });
});

describe('application back navigation', () => {
  it('returns through visited views and preserves the conversation', () => {
    const store = useAppStore.getState();
    store.setView('workspace');
    store.setView('evidence');
    store.goBack();
    expect(useAppStore.getState().view).toBe('workspace');
    store.goBack();
    expect(useAppStore.getState().view).toBe('chat');
    expect(useAppStore.getState().activeSessionKey).toBe('session-a');
    expect(useAppStore.getState().navigationHistory).toEqual([]);
  });

  it('returns from specialist settings before leaving the settings panel', () => {
    const store = useAppStore.getState();
    store.setSidebarPanel('settings');
    store.setSettingsSection('models');
    store.goBack();
    expect(useAppStore.getState().settingsSection).toBe('general');
    expect(useAppStore.getState().sidebarPanel).toBe('settings');
    store.goBack();
    expect(useAppStore.getState().sidebarPanel).toBeNull();
    expect(useAppStore.getState().view).toBe('chat');
  });

  it('reduces an expanded Atelier before navigating away', () => {
    useWorkspaceStore.getState().update('session-a', {mode:'expanded'});
    useAppStore.getState().goBack();
    expect(useWorkspaceStore.getState().sessions['session-a'].mode).toBe('workspace');
    expect(useAppStore.getState().activeSessionKey).toBe('session-a');
  });

  it('reopens the previous chat when Home created a new conversation', () => {
    const loadHistory = vi.fn();
    const switchSession = vi.fn();
    useAppStore.setState({ connection:{
      createSession:(reply: (value: {id:string}) => void) => reply({id:'session-b'}),
      switchSession, loadHistory,
    } as never });
    useAppStore.getState().setView('welcome');
    expect(useAppStore.getState().activeSessionKey).toBe('session-b');
    useAppStore.getState().goBack();
    expect(useAppStore.getState().activeSessionKey).toBe('session-a');
    expect(switchSession).toHaveBeenLastCalledWith('session-a');
    expect(loadHistory).toHaveBeenCalledOnce();
  });
});
