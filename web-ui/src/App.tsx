import { useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { Layout } from '@/components/Layout';
import { LoginPage } from '@/components/LoginPage';
import { WelcomeScreen } from '@/components/WelcomeScreen';
import { ChatView } from '@/components/ChatView';
import { Workspace } from '@/components/Workspace';
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
      // Streaming only while a run is actually in flight. Startup frames
      // (brain.status etc.) must not leave the typing indicator stuck on.
      const runEvents = [
        'task.received', 'subtask.started', 'brain.started', 'thinking',
      ];
      const endEvents = [
        'task.complete', 'task.failed', 'subtask.complete', 'subtask.failed',
        'brain.complete', 'done',
      ];
      if (endEvents.includes(activity.type) || activity.phase === 'end') {
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
        ) : (
          <ChatView key="chat" />
        )}
      </AnimatePresence>
    </Layout>
  );
}
