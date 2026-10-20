import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
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
        // A persisted session key that the server does not know (e.g.
        // a stale mock key from an older build: 'default', 'coding') is
        // discarded — a fresh session starts instead of minting junk ids.
        const legacyKey = store.activeSessionKey && !store.activeSessionKey.startsWith('sess-');
        if ((!store.activeSessionKey || legacyKey) && connection.createSession) {
          connection.createSession((session) => {
            if (session?.id) {
              useAppStore.getState().setActiveSessionKey(session.id);
            }
          });
        }
      }
    });

    connection.on('onSessionChanged', ({ sessionId, deleted, title }) => {
      const store = useAppStore.getState();
      if (deleted) store.forgetSession(sessionId);
      else if (title) store.setSessions(store.sessions.map((session) => session.key === sessionId ? { ...session, title } : session));
    });

    connection.on('onMessage', (msg) => {
      if (useAppStore.getState().view === 'welcome') return;
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
      useAppStore.getState().refreshSessions();
    });

    connection.on('onResumeCatchUp', (messages, sessionId, asOf) => {
      const current = useAppStore.getState();
      if (sessionId !== current.activeSessionKey) return;
      current.restoreSessionHistory(sessionId, messages, asOf);
    });
    connection.on('onHistoryError', (error, sessionId) => {
      if (sessionId === useAppStore.getState().activeSessionKey) {
        useAppStore.setState({ historyError: error });
      }
    });

    connection.on('onStreamDelta', (delta) => {
      if (useAppStore.getState().view === 'welcome') return;
      appendStreamingText(delta.text);
    });

    connection.on('onAgentActivity', (activity) => {
      useAppStore.getState().addAgentActivity(activity);
      useAppStore.getState().applyRunEvent(activity);
      // Streaming manual runs: live output + final verdict.
      if (activity.type === 'fs.run_output' || activity.type === 'fs.run_result') {
        useAppStore.getState().applyFsRunEvent(activity);
      }
      // The agent created a board task → pull the persistent board.
      if (activity.type === 'taskboard.task_created') {
        useAppStore.getState().fetchBoardTasks();
      }
      const sessionId = activity.detail?.session_id;
      const current = useAppStore.getState();
      if (sessionId && sessionId !== current.activeSessionKey) return;
      if (current.view === 'welcome') return;
      // Contract approval flow (Phase B): a proposal arrives → show the
      // card; a verdict arrives → the card is resolved.
      if (activity.type === 'contracts.proposal') {
        const d = activity.detail || {};
        if (d.design_id && d.plan_id) {
          useAppStore.getState().setContractProposal({
            designId: d.design_id,
            planId: d.plan_id,
            request: d.user_request || '',
            contracts: Array.isArray(d.contracts) ? d.contracts : [],
            ...(d.project_target ? { target: d.project_target } : {}),
          });
        }
      } else if (activity.type === 'contracts.approved' || activity.type === 'contracts.rejected') {
        if (useAppStore.getState().contractProposal?.planId === activity.detail?.plan_id) {
          useAppStore.getState().setContractProposal(null);
        }
      } else if (activity.type === 'contracts.approval_failed') {
        if (useAppStore.getState().contractProposal?.planId === activity.detail?.plan_id) {
          useAppStore.setState({ contractSending: false,
            contractError: String(activity.detail?.error || 'Approbation non enregistrée') });
        }
      }
      // Typing belongs to assistant text generation, never task progress.
      // The session-scoped RunPanel is the sole execution indicator.
      // The front brain owns the final chat reply (including failures).
      // task.failed already docks an error card; do not add a second reply.
    });

    connection.on('onRunEnd', () => {
      if (useAppStore.getState().view === 'welcome') return;
      finalizeStreaming();
      useAppStore.getState().refreshSessions();
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
        <motion.div
          key={view}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="h-full"
        >
        {view === 'welcome' ? (
          <WelcomeScreen />
        ) : view === 'workspace' ? (
          <Workspace />
        ) : view === 'discover' ? (
          <DiscoverView />
        ) : view === 'tasks' ? (
          <TasksView />
        ) : view === 'brains' ? (
          <BrainsView />
        ) : view === 'evidence' ? (
          <EvidenceView />
        ) : (
          <ChatView />
        )}
        </motion.div>
      </AnimatePresence>
      {/* Global file viewer — opened from the run panel or the explorer */}
      <CodeViewer />
    </Layout>
  );
}
