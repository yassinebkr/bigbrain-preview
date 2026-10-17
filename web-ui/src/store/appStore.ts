import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Message, Attachment, Session, Settings, Theme, View, ConnectionStatus, SidebarPanel, User, CanvasOp, Task } from '@/types';
import type { ConnectionLike } from '@/lib/connection';

export interface AgentActivity {
  type: string;
  phase?: string;
  name?: string;
  detail?: any;
  ts: number;
}

// One orchestrated run (task → subtasks → complete/failed), derived from
// bus events. Drives RunPanel: visibility follows the RUN STATE, never a
// per-event timer — that is what made the old pills blink on and off.
export interface RunStep {
  id: string;
  brain?: string;
  description: string;
  status: 'running' | 'done' | 'failed';
  durationMs?: number;
  // Live output streamed by the brain while it works
  // (execution.output events, capped tail).
  liveOutput?: string;
}

export interface RunVerification {
  runId: string;
  verdict: 'passed' | 'failed' | 'inconclusive';
  attempt?: number;
  stages: { name: string; status: string }[];
}

export interface RunState {
  sessionId: string;
  id: string;
  description: string;
  status: 'running' | 'done' | 'failed' | 'cancelled';
  startedAt: number;
  finishedAt?: number;
  steps: RunStep[];
  files: { path: string; ts: number }[];
  error?: string;
  verification?: RunVerification;
  projectName?: string;
  projectPath?: string;
  entryPoint?: string;
  deliverableType?: string;
  previewUrl?: string;
  runnable?: boolean;
  awaitingApproval?: boolean;
}

interface AppState {
  // Auth
  isAuthenticated: boolean;
  isAuthLoading: boolean;
  authError: string | null;
  user: User | null;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
  setUser: (user: User | null) => void;
  clearAuthError: () => void;

  // Theme
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;

  // View
  view: View;
  setView: (view: View) => void;

  // Messages
  messages: Message[];
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  clearMessages: () => void;
  setMessages: (messages: Message[]) => void;

  // Input
  inputText: string;
  setInputText: (text: string) => void;

  // Streaming
  isStreaming: boolean;
  streamingText: string;
  setIsStreaming: (streaming: boolean) => void;
  setStreamingText: (text: string) => void;
  appendStreamingText: (text: string) => void;
  finalizeStreaming: () => void;

  // Connection
  connectionStatus: ConnectionStatus;
  setConnectionStatus: (status: ConnectionStatus) => void;
  connection: ConnectionLike | null;
  setConnection: (conn: ConnectionLike) => void;

  // Voice
  isRecording: boolean;
  setRecording: (recording: boolean) => void;

  // Attachments
  attachments: Attachment[];
  addAttachment: (attachment: Attachment) => void;
  removeAttachment: (id: string) => void;
  clearAttachments: () => void;

  // BigBrain bus activity feed (brain status, task/subtask events) —
  // consumed by BrainStatusPanel and TaskBoard (docs/WEBUI-APLOT-PORT.md).
  agentActivities: AgentActivity[];
  addAgentActivity: (activity: Omit<AgentActivity, 'ts'>) => void;

  // Orchestrated run state (task/subtask/file events) — RunPanel v2.
  activeRun: RunState | null;
  // Finished runs are timeline records, grouped by their chat session.
  completedRuns: RunState[];
  applyRunEvent: (activity: Omit<AgentActivity, 'ts'>) => void;
  runPanelOpen: boolean;
  setRunPanelOpen: (open: boolean) => void;
  // The user closed the run panel (X). The NudgeBar reads this to surface
  // a REMINDER only when the record is hidden — never as a duplicate of
  // the visible panel.
  runPanelDismissed: boolean;
  setRunPanelDismissed: (dismissed: boolean) => void;

  // Working project (mirrors /api/fs/current-project) — sandbox nudge.
  currentProject: string | null;
  setCurrentProject: (project: string | null) => void;
  pendingOpenFile: string | null;
  setPendingOpenFile: (path: string | null) => void;

  // In-chat code viewer (files written by the agent).
  viewerFilePath: string | null;
  openFileViewer: (path: string) => void;
  closeFileViewer: () => void;

  // Contract approval (Phase B): before the agent writes code, it proposes
  // checkable contracts; the user approves → execution resumes, the
  // approval is traced in the evidence DesignSpec.
  contractProposal: { designId: string; planId: string; request: string; contracts: string[] } | null;
  contractSending: boolean;
  setContractProposal: (
    proposal: { designId: string; planId: string; request: string; contracts: string[] } | null
  ) => void;
  sendContractDecision: (approve: boolean) => Promise<void>;

  // Sidebar
  sidebarOpen: boolean;
  sidebarPanel: SidebarPanel;
  setSidebarOpen: (open: boolean) => void;
  setSidebarPanel: (panel: SidebarPanel) => void;
  toggleSidebarPanel: (panel: SidebarPanel) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;

  // Command Palette
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;

  // Settings
  settings: Settings;
  toggleSetting: (key: keyof Settings) => void;

  // Sessions
  sessions: Session[];
  activeSessionKey: string;
  setSessions: (sessions: Session[]) => void;
  setActiveSessionKey: (key: string) => void;
  switchSession: (key: string) => void;
  refreshSessions: () => void;
  startNewSession: () => void;
  openSession: (key: string) => void;

  // Canvas
  canvasOps: CanvasOp[];
  addCanvasOp: (op: CanvasOp) => void;
  clearCanvasOps: () => void;

  // Workspace
  tasks: Task[];
  addTask: (task: Task) => void;
  fetchBoardTasks: () => Promise<void>;
  createBoardTask: (task: Partial<Task>) => Promise<void>;
  updateTask: (id: string, updates: Partial<Task>) => void;
  deleteTask: (id: string) => void;
  workspaceView: 'files' | 'tasks' | 'research';
  setWorkspaceView: (view: 'files' | 'tasks' | 'research') => void;

  // Proactive nudges (Phase B) — real suggestions derived from run state.
  // Only the DISMISSAL is stored; the nudge itself is always derived.
  dismissedNudges: string[];
  dismissNudge: (key: string) => void;

  // Streaming manual runs (POST /api/fs/run): the server streams
  // fs.run_output deltas and a final fs.run_result over the WS. The
  // output appears AS IT IS PRODUCED instead of at the end.
  liveRuns: Record<string, { out: string; err: string; done: boolean; result: any }>;
  applyFsRunEvent: (activity: Omit<AgentActivity, 'ts'>) => void;

  // Actions
  sendMessage: () => void;
  stopGeneration: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Auth
      isAuthenticated: !!localStorage.getItem('aplot_auth_token'),
      isAuthLoading: false,
      authError: null,
      user: null,
      loginWithToken: async (token: string) => {
        set({ isAuthLoading: true, authError: null });
        try {
          // Save token to localStorage
          localStorage.setItem('aplot_auth_token', token);
          set({ isAuthenticated: true, isAuthLoading: false, authError: null });
          // Decode JWT to get user info without server call
          try {
            const parts = token.split('.');
            if (parts.length === 3) {
              const payload = JSON.parse(atob(parts[1]));
              set({ user: { id: payload.sub || payload.id || '', name: payload.name || 'User', email: payload.email || '', role: payload.role } });
            }
          } catch { /* JWT decode is best-effort */ }
          // Also try to fetch user info from server
          try {
            const res = await fetch('/api/v2/auth/me', {
              headers: { Authorization: `Bearer ${token}` },
              credentials: 'same-origin',
            });
            if (res.ok) {
              const user = await res.json();
              set({ user: { id: user.id || '', name: user.name || 'User', email: user.email || '', role: user.role } });
            }
          } catch { /* user info fetch is best-effort */ }
        } catch (err: any) {
          localStorage.removeItem('aplot_auth_token');
          set({ isAuthLoading: false, authError: err.message || 'Authentication failed. Please try again.' });
        }
      },
      logout: () => {
        localStorage.removeItem('aplot_auth_token');
        get().connection?.disconnect();
        set({ isAuthenticated: false, user: null, authError: null, messages: [], view: 'welcome', connectionStatus: 'disconnected' });
      },
      setUser: (user) => set({ user }),
      clearAuthError: () => set({ authError: null }),

      // Theme
      theme: 'dark',
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((state) => ({ theme: state.theme === 'dark' ? 'light' : 'dark' })),

      // View
      view: 'welcome',
      setView: (view) => set({ view }),

      // Messages
      messages: JSON.parse(localStorage.getItem('aplot_messages') || '[]'),
      addMessage: (message) => set((state) => {
        const newMessages = [...state.messages, message];
        localStorage.setItem('aplot_messages', JSON.stringify(newMessages));
        return { messages: newMessages };
      }),
      updateMessage: (id, updates) => set((state) => {
        const newMessages = state.messages.map((m) => (m.id === id ? { ...m, ...updates } : m));
        localStorage.setItem('aplot_messages', JSON.stringify(newMessages));
        return { messages: newMessages };
      }),
      clearMessages: () => {
        localStorage.removeItem('aplot_messages');
        set({ messages: [] });
      },
      setMessages: (messages) => {
        localStorage.setItem('aplot_messages', JSON.stringify(messages));
        set({ messages });
      },

      // Input
      inputText: '',
      setInputText: (text) => set({ inputText: text }),

      // Streaming
      isStreaming: false,
      streamingText: '',
      setIsStreaming: (isStreaming) => set({ isStreaming }),
      setStreamingText: (streamingText) => set({ streamingText }),
      appendStreamingText: (text) => set((state) => ({ streamingText: state.streamingText + text })),
      finalizeStreaming: () => set((state) => {
        // An empty streaming buffer must not render a blank bubble —
        // repeated run events during a failed task used to stack empties.
        if (!state.streamingText || !state.streamingText.trim()) {
          return { isStreaming: false, streamingText: '' };
        }
        const finalMessage: Message = { id: `ai-${Date.now()}`, role: 'assistant', content: state.streamingText, timestamp: Date.now() };
        return { isStreaming: false, streamingText: '', messages: [...state.messages, finalMessage] };
      }),

      // Connection
      connectionStatus: 'connecting',
      setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
      connection: null,
      setConnection: (connection) => set({ connection }),

      // Voice
      isRecording: false,
      setRecording: (isRecording) => set({ isRecording }),

      // Attachments
      attachments: [],
      addAttachment: (attachment) => set((state) => ({ attachments: [...state.attachments, attachment] })),
      removeAttachment: (id) => set((state) => ({ attachments: state.attachments.filter((a) => a.id !== id) })),
      clearAttachments: () => set({ attachments: [] }),

      agentActivities: [],
      addAgentActivity: (activity) => set((state) => ({
        agentActivities: [...state.agentActivities.slice(-49), { ...activity, ts: Date.now() }],
      })),

      activeRun: null,
      completedRuns: [],
      runPanelOpen: false,
      setRunPanelOpen: (runPanelOpen) => set({ runPanelOpen }),
      runPanelDismissed: false,
      setRunPanelDismissed: (runPanelDismissed) => set({ runPanelDismissed }),
      currentProject: null,
      setCurrentProject: (currentProject) => set({ currentProject }),
      pendingOpenFile: null,
      setPendingOpenFile: (pendingOpenFile) => set({ pendingOpenFile }),
      viewerFilePath: null,
      openFileViewer: (path) => set({ viewerFilePath: path }),
      closeFileViewer: () => set({ viewerFilePath: null }),

      contractProposal: null,
      contractSending: false,
      setContractProposal: (proposal) =>
        set({ contractProposal: proposal, contractSending: false }),
      sendContractDecision: async (approve) => {
        const proposal = get().contractProposal;
        if (!proposal || get().contractSending) return;
        set({ contractSending: true });
        try {
          const r = await fetch('/api/contracts/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              design_id: proposal.designId,
              plan_id: proposal.planId,
              approve,
            }),
          });
          if (r.ok) {
            // The orchestrator also broadcasts contracts.approved /
            // contracts.rejected which clear the card — clearing here
            // makes the UI immediate; both are idempotent.
            set({ contractProposal: null, contractSending: false });
          } else {
            set({ contractSending: false });
          }
        } catch {
          set({ contractSending: false });
        }
      },

      // Fold bus events into the current run. Pure state machine:
      // task.routing opens a run immediately; subtask.* upsert steps;
      // workspace.file_written collects files; task.complete/failed
      // docks the finished record into its conversation timeline.
      applyRunEvent: (activity) => set((state) => {
        const d = activity.detail || {};
        const run = state.activeRun;
        switch (activity.type) {
          case 'task.routing': {
            const sessionId = String(d.session_id || state.activeSessionKey || '');
            const fresh: RunState = {
              sessionId,
              id: `routing-${Date.now()}`,
              description: String(d.description || 'Preparing task'),
              status: 'running',
              startedAt: Date.now(),
              steps: [],
              files: [],
            };
            return { activeRun: fresh, runPanelDismissed: false };
          }
          case 'task.received': {
            const fresh: RunState = {
              sessionId: String(d.session_id || run?.sessionId || state.activeSessionKey || ''),
              id: d.task_id || `run-${Date.now()}`,
              description: String(d.description || 'Task'),
              status: 'running',
              startedAt: Date.now(),
              steps: [],
              files: [],
            };
            return { activeRun: fresh, runPanelDismissed: false };
          }
          case 'contracts.proposal': {
            const sessionId = String(d.session_id || run?.sessionId || state.activeSessionKey || '');
            if (run && run.status === 'running') {
              return { activeRun: { ...run, sessionId, awaitingApproval: true }, runPanelDismissed: false };
            }
            const fresh: RunState = {
              sessionId,
              id: String(d.plan_id || `approval-${Date.now()}`),
              description: String(d.user_request || 'Awaiting contract approval'),
              status: 'running',
              awaitingApproval: true,
              startedAt: Date.now(),
              steps: [],
              files: [],
            };
            return { activeRun: fresh, runPanelDismissed: false };
          }
          case 'subtask.started': {
            if (!run || run.status !== 'running') return state;
            const step: RunStep = {
              id: String(d.subtask_id || `step-${run.steps.length}`),
              brain: d.brain,
              description: String(d.description || 'working').slice(0, 120),
              status: 'running',
            };
            return {
              activeRun: {
                ...run,
                awaitingApproval: false,
                steps: [...run.steps.filter((s) => s.id !== step.id), step],
              },
            };
          }
          case 'execution.output': {
            // The brain streams its program output while it runs —
            // attach it to the matching step so the user sees the work.
            if (!run || run.status !== 'running') return state;
            const delta = String(d.delta || '');
            if (!delta) return state;
            const targetId = d.subtask_id
              ? String(d.subtask_id)
              : (run.steps.find((s) => s.status === 'running')?.id || null);
            if (!targetId) return state;
            return {
              activeRun: {
                ...run,
                steps: run.steps.map((s) =>
                  s.id === targetId
                    ? { ...s, liveOutput: ((s.liveOutput || '') + delta).slice(-4000) }
                    : s
                ),
              },
            };
          }
          case 'subtask.complete':
          case 'subtask.failed': {
            if (!run || run.status !== 'running') return state;
            const id = String(d.subtask_id || `step-${run.steps.length}`);
            const failed = activity.type === 'subtask.failed';
            const durationMs = typeof d.execution_time === 'number' ? d.execution_time * 1000 : undefined;
            const exists = run.steps.some((s) => s.id === id);
            const steps = exists
              ? run.steps.map((s) =>
                  s.id === id ? { ...s, status: failed ? ('failed' as const) : ('done' as const), durationMs } : s
                )
              : [...run.steps, { id, description: 'subtask', status: failed ? ('failed' as const) : ('done' as const), durationMs }];
            return { activeRun: { ...run, steps } };
          }
          case 'workspace.file_written': {
            if (!run || run.status !== 'running' || !d.path) return state;
            const path = String(d.path);
            if (run.files.some((f) => f.path === path)) return state;
            return { activeRun: { ...run, files: [...run.files, { path, ts: Date.now() }] } };
          }
          case 'verification.run_recorded': {
            // Harness P4: the gate's verdict per attempt, attached to the
            // live run. An orphan event (no active run) is dropped.
            if (!run) return state;
            const verdict = d.verdict === 'passed' || d.verdict === 'failed'
              ? d.verdict : 'inconclusive';
            return {
              activeRun: {
                ...run,
                verification: {
                  runId: String(d.run_id || ''),
                  verdict,
                  attempt: typeof d.attempt === 'number' ? d.attempt : undefined,
                  stages: Array.isArray(d.stages)
                    ? d.stages.map((s: any) => ({
                        name: String(s?.name || ''),
                        status: String(s?.status || ''),
                      }))
                    : [],
                },
              },
            };
          }
          case 'task.complete':
          case 'task.failed':
          case 'task.cancelled': {
            if (!run) return state;
            const status: RunState['status'] =
              activity.type === 'task.complete' ? 'done'
              : activity.type === 'task.cancelled' ? 'cancelled'
              : 'failed';
            return {
              activeRun: null,
              completedRuns: [...state.completedRuns, {
                ...run,
                status,
                finishedAt: Date.now(),
                error: d.error ? String(d.error).slice(0, 200) : run.error,
                projectName: d.project_name ? String(d.project_name) : run.projectName,
                projectPath: d.project_path ? String(d.project_path) : run.projectPath,
                entryPoint: d.entry_point ? String(d.entry_point) : run.entryPoint,
                deliverableType: d.deliverable_type ? String(d.deliverable_type) : run.deliverableType,
                previewUrl: d.preview_url ? String(d.preview_url) : run.previewUrl,
                runnable: typeof d.runnable === 'boolean' ? d.runnable : run.runnable,
              }].slice(-100),
            };
          }
          default:
            return state;
        }
      }),

      // Sidebar
      sidebarOpen: false,
      sidebarPanel: null,
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      setSidebarPanel: (sidebarPanel) => set({ sidebarPanel, sidebarOpen: sidebarPanel !== null }),
      toggleSidebarPanel: (panel) => set((state) => {
        const isSamePanel = state.sidebarPanel === panel;
        return { sidebarPanel: isSamePanel ? null : panel, sidebarOpen: !isSamePanel };
      }),
      mobileSidebarOpen: false,
      setMobileSidebarOpen: (mobileSidebarOpen) => set({ mobileSidebarOpen }),

      // Command Palette
      commandPaletteOpen: false,
      setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),

      // Settings
      settings: { genui: false, autoSpeech: false },
      toggleSetting: (key) => set((state) => ({ settings: { ...state.settings, [key]: !state.settings[key] } })),

      // Sessions — real server-side conversations (data/sessions/).
      sessions: [],
      activeSessionKey: '',
      setSessions: (sessions) => set({ sessions }),
      setActiveSessionKey: (activeSessionKey) => set({ activeSessionKey }),
      switchSession: (key) => {
        get().connection?.switchSession(key);
        // A run belongs to its conversation — the record of the previous
        // one must not follow the user into the next.
        set({ activeSessionKey: key, messages: [], view: 'welcome',
              runPanelDismissed: false });
      },
      // Pull the session list from the server into the store.
      refreshSessions: () => {
        get().connection?.listSessions?.((list) => {
          set({
            sessions: (list || []).map((s) => ({
              key: s.id,
              title: s.title || 'New conversation',
              timestamp: (s.updated_at || 0) * 1000,
              messageCount: s.message_count || 0,
            })),
          });
        });
      },
      // New conversation: a REAL session on the server.
      startNewSession: () => {
        const conn = get().connection;
        if (conn?.createSession) {
          conn.createSession((session) => {
            if (!session?.id) return;
            set({
              activeSessionKey: session.id,
              messages: [],
              view: 'welcome',
              streamingText: '',
              isStreaming: false,
              runPanelDismissed: false,
            });
            get().refreshSessions();
          });
        } else {
          // Offline: a local blank conversation (kept honest — no fake id).
          set({
            activeSessionKey: '',
            messages: [],
            view: 'welcome',
            streamingText: '',
            isStreaming: false,
            runPanelDismissed: false,
          });
        }
      },
      // Open an existing conversation: load its history from the server.
      openSession: (key) => {
        set({
          activeSessionKey: key,
          sidebarPanel: null,
          messages: [],
          streamingText: '',
          isStreaming: false,
          runPanelDismissed: false,
        });
        get().connection?.loadHistory((frame: any) => {
          if (frame?.ok && frame.payload?.messages) {
            set({
              messages: frame.payload.messages.map((m: any) => ({
                id: m.id || `hist-${Date.now()}-${Math.random()}`,
                role: m.role === 'user' ? 'user' : 'assistant',
                content: m.content,
                timestamp: m.timestamp
                  ? (m.timestamp < 1e12 ? m.timestamp * 1000 : m.timestamp)
                  : Date.now(),
              })),
              view: 'chat',
            });
          }
        }, key);
      },

      // Canvas
      canvasOps: [],
      addCanvasOp: (op) => set((state) => ({ canvasOps: [...state.canvasOps, op] })),
      clearCanvasOps: () => set({ canvasOps: [] }),

      // Workspace — the board starts EMPTY: only real agent tasks (bus
      // events) and manual additions show up. No seed/mock entries.
      tasks: [],
      addTask: (task) => set((state) => ({ tasks: [...state.tasks, task] })),

      // The persistent board lives server-side (data/tasks.json); the
      // store is its view. Server sync is best effort — offline the
      // local operations keep working.
      fetchBoardTasks: async () => {
        try {
          const r = await fetch('/api/tasks');
          if (!r.ok) return;
          const body = await r.json();
          const serverTasks = (body.tasks || []).map((t: any) => ({
            id: t.id,
            title: t.title,
            description: t.description || '',
            status: t.status,
            tags: t.tags || [],
            assignee: t.assignee || 'BigBrain',
            priority: t.priority || 'medium',
            createdAt: (t.createdAt || 0) * 1000,
          }));
          // Server tasks replace the list except offline local tasks
          // (local-*) which have no server counterpart yet.
          const local = get().tasks.filter((t) => t.id.startsWith('local-'));
          set({ tasks: [...local, ...serverTasks] });
        } catch { /* offline: keep the local view */ }
      },
      createBoardTask: async (task) => {
        try {
          const r = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(task),
          });
          if (r.ok) {
            await get().fetchBoardTasks();
            return;
          }
        } catch { /* fall through to local */ }
        // Offline fallback: local task (honest — no fake server id).
        get().addTask({
          id: `local-${Date.now()}`,
          title: task.title || 'Task',
          description: task.description || '',
          status: task.status || 'todo',
          tags: task.tags || ['manual'],
          assignee: task.assignee || 'You',
          priority: task.priority || 'medium',
          createdAt: Date.now(),
        });
      },

      // The board shows ONLY persistent user tasks (server + offline
      // local). Agent runs in flight are visible in the RunPanel —
      // mirroring them here flipped cards in-progress→done and
      // confused them with real tasks.
      updateTask: (id, updates) => {
        set((state) => ({ tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)) }));
        // Persisted board task → sync the server (best effort).
        if (id.startsWith('task-')) {
          fetch('/api/tasks', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, updates }),
          }).catch(() => { /* offline: local view already updated */ });
        }
      },
      deleteTask: (id) => {
        set((state) => ({ tasks: state.tasks.filter((t) => t.id !== id) }));
        if (id.startsWith('task-')) {
          fetch(`/api/tasks?id=${encodeURIComponent(id)}`, { method: 'DELETE' })
            .catch(() => { /* offline: local view already updated */ });
        }
      },
      workspaceView: 'files',
      setWorkspaceView: (workspaceView) => set({ workspaceView }),

      // Proactive nudges — dismissed keys are persisted so a suggestion
      // the user closed does not come back on the next render/reload.
      dismissedNudges: [],
      dismissNudge: (key) =>
        set((state) => ({
          dismissedNudges: [...new Set([...state.dismissedNudges, key])].slice(-50),
        })),

      liveRuns: {},
      applyFsRunEvent: (activity) => set((state) => {
        const d = activity.detail || {};
        const runId = d.runId;
        if (!runId) return state;
        if (activity.type === 'fs.run_output') {
          const current = state.liveRuns[runId] || { out: '', err: '', done: false, result: null };
          const delta = String(d.delta || '');
          const stream = d.stream === 'err' ? 'err' : 'out';
          const merged = stream === 'err'
            ? { ...current, err: (current.err + delta).slice(-20000) }
            : { ...current, out: (current.out + delta).slice(-20000) };
          return { liveRuns: { ...state.liveRuns, [runId]: merged } };
        }
        if (activity.type === 'fs.run_result') {
          const { runId: _drop, ...result } = d;
          const current = state.liveRuns[runId] || { out: '', err: '', done: false, result: null };
          return {
            liveRuns: {
              ...state.liveRuns,
              [runId]: { ...current, done: true, result },
            },
          };
        }
        return state;
      }),

      // Actions
      sendMessage: () => {
        const state = get();
        const text = state.inputText.trim();
        if (!text && state.attachments.length === 0) return;
        const userMessage: Message = { id: `user-${Date.now()}`, role: 'user', content: text, timestamp: Date.now(), attachments: state.attachments.length > 0 ? [...state.attachments] : undefined };
        // Sending from the home page ALWAYS starts a new conversation —
        // the previous transcript must not bleed into it.
        const isNewConversation = state.view === 'welcome';
        set((s) => ({
          messages: isNewConversation ? [userMessage] : [...s.messages, userMessage],
          inputText: '',
          attachments: [],
          view: 'chat',
          isStreaming: true,
          streamingText: '',
        }));
        // Attachments: upload the files first (POST /api/attachments),
        // then send the message with server refs — the front brain
        // records them in persistent memory. Offline: the message goes
        // out without the files (upload failure never blocks the text).
        (async () => {
          const refs: { id: string; name: string; type: string }[] = [];
          for (const att of state.attachments) {
            if (!att.file) continue;
            try {
              const body = new FormData();
              body.append('file', att.file, att.name);
              const r = await fetch('/api/attachments', { method: 'POST', body });
              if (r.ok) {
                const rec = await r.json();
                refs.push({ id: rec.id, name: rec.name, type: rec.type });
              }
            } catch { /* offline: text still sends */ }
          }
          state.connection?.send(text, refs,
                                  state.activeSessionKey || undefined);
        })();
      },

      // Stop button: cancel server-side (front brain stream + orchestrated
      // run), then close the streaming bubble locally with whatever text
      // already arrived (finalizeStreaming keeps it as a message).
      stopGeneration: () => {
        get().connection?.cancel?.();
        get().finalizeStreaming();
      },
    }),
    {
      name: 'aplot-ai-storage',
      partialize: (state) => ({
        theme: state.theme,
        settings: state.settings,
        activeSessionKey: state.activeSessionKey,
        // The last run is the RECORD of what the agent did (steps, files
        // written) — it must survive a page reload, not just tab switches.
        activeRun: state.activeRun,
        completedRuns: state.completedRuns,
        // Layout persistence: where the user was working (view + workspace
        // tab + the open code file) survives a reload.
        view: state.view,
        workspaceView: state.workspaceView,
        viewerFilePath: state.viewerFilePath,
        dismissedNudges: state.dismissedNudges,
      }),
    }
  )
);
