import { useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { Layout } from '@/components/Layout';
import { LoginPage } from '@/components/LoginPage';
import { WelcomeScreen } from '@/components/WelcomeScreen';
import { ChatView } from '@/components/ChatView';
import { Workspace } from '@/components/Workspace';
import { DiscoverView } from '@/components/DiscoverView';
import { TasksView } from '@/components/TasksView';
import { BrainsView } from '@/components/BrainsView';
import { EvidenceView } from '@/components/EvidenceView';
import { CodeViewer } from '@/components/CodeViewer';
import { createConnection } from '@/lib/connection';

const connection = createConnection();

export default function App() {
  const {
    isAuthenticated,
    view,
    setConnectionStatus,
    addMessage,
    appendStreamingText,
    setIsStreaming,
    finalizeStreaming,
    setCommandPaletteOpen,
    commandPaletteOpen,
    setConnection,
    setUser,
    addCanvasOp,
  } = useAppStore();

  // Set connection in store
  useEffect(() => {
    setConnection(connection);
  }, [setConnection]);

  // WebSocket connection + callbacks — only when authenticated
  useEffect(() => {
    if (!isAuthenticated) return;

    connection.on('onStatusChange', (status) => {
      setConnectionStatus(status as 'connected' | 'connecting' | 'disconnected');
      // Real sessions: list them on connect, and start one if the client
      // has none (first visit / cleared storage) so messages have a home.
      if (status === 'connected') {
        const store = useAppStore.getState();
        store.refreshSessions();
        if (!store.activeSessionKey && connection.createSession) {
          connection.createSession((session) => {
            if (session?.id && !useAppStore.getState().activeSessionKey) {
              useAppStore.getState().setActiveSessionKey(session.id);
            }
          });
        }
      }
    });

    connection.on('onMessage', (msg) => {
      // Skip empty payloads (e.g. system status frames): they used to
      // render as a blank assistant bubble.
      if (!msg.text || !msg.text.trim()) return;
      // A reply arrived: any pending streaming state is over.
      finalizeStreaming();
      addMessage({
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: msg.text,
        timestamp: Date.now(),
      });
    });

    connection.on('onStreamDelta', (delta) => {
      appendStreamingText(delta.text);
    });

    connection.on('onAgentActivity', (activity) => {
      useAppStore.getState().addAgentActivity(activity);
      useAppStore.getState().applyBusActivity(activity);
      useAppStore.getState().applyRunEvent(activity);
      // Streaming only while a run is actually in flight. Startup frames
      // (brain.status etc.) must not leave the typing indicator stuck on.
      const runEvents = [
        'task.received', 'subtask.started', 'brain.started', 'thinking',
      ];
      const endEvents = [
        'task.complete', 'task.failed', 'subtask.complete', 'subtask.failed',
        'brain.complete', 'done',
      ];
      if (activity.type === 'task.failed') {
        finalizeStreaming();
        const detail = activity.detail || {};
        const subErrors = (detail.failed_subtasks || [])
          .map((st: any) => st.error)
          .filter(Boolean)
          .slice(0, 2);
        const reason = [detail.error, ...subErrors].filter(Boolean).join(' · ');
        useAppStore.getState().addMessage({
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Task failed: ${reason || 'unknown error'}`,
          timestamp: Date.now(),
        });
      } else if (endEvents.includes(activity.type) || activity.phase === 'end') {
        finalizeStreaming();
      } else if (runEvents.includes(activity.type)) {
        setIsStreaming(true);
      }
    });

    connection.on('onRunEnd', () => {
      finalizeStreaming();
    });

    connection.on('onCanvasUpdate', (payload) => {
      if (payload.ops) {
        payload.ops.forEach((op: any) => addCanvasOp(op));
      }
    });

    connection.on('onUserInfo', (user) => {
      setUser({ id: user.id || '', name: user.name || '', email: user.email || '', role: user.role });
    });

    connection.connect();

    return () => {
      connection.disconnect();
    };
  }, [isAuthenticated]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      if (e.key === 'Escape' && commandPaletteOpen) {
        setCommandPaletteOpen(false);
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'l') {
        e.preventDefault();
        useAppStore.getState().toggleTheme();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        useAppStore.getState().setView('welcome');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [commandPaletteOpen, setCommandPaletteOpen]);

  // Not authenticated → show login page
  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <Layout>
      <AnimatePresence mode="wait">
        {view === 'welcome' ? (
          <WelcomeScreen key="welcome" />
        ) : view === 'workspace' ? (
          <Workspace key="workspace" />
        ) : view === 'discover' ? (
          <DiscoverView key="discover" />
        ) : view === 'tasks' ? (
          <TasksView key="tasks" />
        ) : view === 'brains' ? (
          <BrainsView key="brains" />
        ) : view === 'evidence' ? (
          <EvidenceView key="evidence" />
        ) : (
          <ChatView key="chat" />
        )}
      </AnimatePresence>
      {/* Global file viewer — opened from the run panel or the explorer */}
      <CodeViewer />
    </Layout>
  );
}
