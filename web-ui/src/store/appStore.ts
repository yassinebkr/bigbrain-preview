import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Message, Attachment, Session, Settings, Theme, View, ConnectionStatus, SidebarPanel, User, CanvasOp, FileItem, Task, TaskStatus } from '@/types';
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
}

export interface RunState {
  id: string;
  description: string;
  status: 'running' | 'done' | 'failed' | 'cancelled';
  startedAt: number;
  finishedAt?: number;
  steps: RunStep[];
  files: { path: string; ts: number }[];
  error?: string;
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
  applyRunEvent: (activity: Omit<AgentActivity, 'ts'>) => void;
  runPanelOpen: boolean;
  setRunPanelOpen: (open: boolean) => void;

  // Working project (mirrors /api/fs/current-project) — sandbox nudge.
  currentProject: string | null;
  setCurrentProject: (project: string | null) => void;
  pendingOpenFile: string | null;
  setPendingOpenFile: (path: string | null) => void;

  // In-chat code viewer (files written by the agent).
  viewerFilePath: string | null;
  openFileViewer: (path: string) => void;
  closeFileViewer: () => void;

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

  // Canvas
  canvasOps: CanvasOp[];
  addCanvasOp: (op: CanvasOp) => void;
  clearCanvasOps: () => void;

  // Workspace
  files: FileItem[];
  selectedFileId: string | null;
  tasks: Task[];
  setSelectedFileId: (id: string | null) => void;
  addFile: (file: FileItem) => void;
  deleteFile: (id: string) => void;
  addTask: (task: Task) => void;
  applyBusActivity: (activity: Omit<AgentActivity, 'ts'>) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  deleteTask: (id: string) => void;
  workspaceView: 'files' | 'tasks' | 'research';
  setWorkspaceView: (view: 'files' | 'tasks' | 'research') => void;

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
      runPanelOpen: false,
      setRunPanelOpen: (runPanelOpen) => set({ runPanelOpen }),
      currentProject: null,
      setCurrentProject: (currentProject) => set({ currentProject }),
      pendingOpenFile: null,
      setPendingOpenFile: (pendingOpenFile) => set({ pendingOpenFile }),
      viewerFilePath: null,
      openFileViewer: (path) => set({ viewerFilePath: path }),
      closeFileViewer: () => set({ viewerFilePath: null }),

      // Fold bus events into the current run. Pure state machine:
      // task.received opens a run; subtask.* upsert steps;
      // workspace.file_written collects files; task.complete/failed
      // closes it (the panel lingers on the summary afterwards).
      applyRunEvent: (activity) => set((state) => {
        const d = activity.detail || {};
        const run = state.activeRun;
        switch (activity.type) {
          case 'task.received': {
            const fresh: RunState = {
              id: d.task_id || `run-${Date.now()}`,
              description: String(d.description || 'Task').slice(0, 140),
              status: 'running',
              startedAt: Date.now(),
              steps: [],
              files: [],
            };
            return { activeRun: fresh };
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
                steps: [...run.steps.filter((s) => s.id !== step.id), step],
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
          case 'task.complete':
          case 'task.failed':
          case 'task.cancelled': {
            if (!run) return state;
            const status =
              activity.type === 'task.complete' ? 'done'
              : activity.type === 'task.cancelled' ? 'cancelled'
              : 'failed';
            return {
              activeRun: {
                ...run,
                status,
                finishedAt: Date.now(),
                error: d.error ? String(d.error).slice(0, 200) : run.error,
              },
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

      // Sessions
      sessions: [
        { key: 'default', title: 'General Conversation', timestamp: Date.now(), messageCount: 0 },
        { key: 'coding', title: 'Coding Help', timestamp: Date.now() - 86400000, messageCount: 12 },
        { key: 'trip', title: 'Trip Planning', timestamp: Date.now() - 172800000, messageCount: 8 },
      ],
      activeSessionKey: 'default',
      setSessions: (sessions) => set({ sessions }),
      setActiveSessionKey: (activeSessionKey) => set({ activeSessionKey }),
      switchSession: (key) => {
        get().connection?.switchSession(key);
        set({ activeSessionKey: key, messages: [], view: 'welcome' });
      },

      // Canvas
      canvasOps: [],
      addCanvasOp: (op) => set((state) => ({ canvasOps: [...state.canvasOps, op] })),
      clearCanvasOps: () => set({ canvasOps: [] }),

      // Workspace
      files: [
        { id: 'root', name: 'Home', type: 'folder', modifiedAt: Date.now(), parentId: null },
        { id: 'docs', name: 'Documents', type: 'folder', modifiedAt: Date.now() - 86400000, parentId: 'root' },
        { id: 'proj', name: 'Projects', type: 'folder', modifiedAt: Date.now() - 172800000, parentId: 'root' },
        { id: 'research', name: 'Research', type: 'folder', modifiedAt: Date.now() - 259200000, parentId: 'root' },
        { id: 'file1', name: 'README.md', type: 'file', size: 2048, modifiedAt: Date.now() - 3600000, parentId: 'docs' },
        { id: 'file2', name: 'notes.txt', type: 'file', size: 1024, modifiedAt: Date.now() - 7200000, parentId: 'docs' },
        { id: 'file3', name: 'app.tsx', type: 'file', size: 5120, modifiedAt: Date.now() - 10800000, parentId: 'proj' },
        { id: 'file4', name: 'analysis.pdf', type: 'file', size: 102400, modifiedAt: Date.now() - 86400000, parentId: 'research' },
      ],
      selectedFileId: null,
      tasks: [
        { id: 't1', title: 'Implement auth flow', description: 'Add login page and token management', status: 'done', tags: ['auth', 'frontend'], assignee: 'AI Agent', priority: 'high', createdAt: Date.now() - 86400000 },
        { id: 't2', title: 'Build GenUI canvas', description: 'Port canvas renderer to React', status: 'in-progress', tags: ['genui', 'canvas'], assignee: 'AI Agent', priority: 'high', createdAt: Date.now() - 43200000 },
        { id: 't3', title: 'Voice recording', description: 'Add mic support with transcription', status: 'in-progress', tags: ['voice', 'chat'], assignee: 'AI Agent', priority: 'medium', createdAt: Date.now() - 36000000 },
        { id: 't4', title: 'Workspace desktop', description: 'File explorer + research bar + tasks', status: 'todo', tags: ['workspace', 'ui'], assignee: 'AI Agent', priority: 'medium', createdAt: Date.now() - 18000000 },
      ],
      setSelectedFileId: (id) => set({ selectedFileId: id }),
      addFile: (file) => set((state) => ({ files: [...state.files, file] })),
      deleteFile: (id) => set((state) => ({ files: state.files.filter((f) => f.id !== id) })),
      addTask: (task) => set((state) => ({ tasks: [...state.tasks, task] })),

      // Bus task events (orchestrator) mapped onto the TaskBoard slice —
      // agent tasks live in the same board as manual ones; drag & drop
      // still works locally (updateTask overrides).
      applyBusActivity: (activity) => set((state) => {
        const d = activity.detail || {};
        const taskId = d.task_id;
        if (!taskId) return state;
        const existing = state.tasks.find((t) => t.id === taskId);
        const ensure = (status: TaskStatus, title?: string, description?: string): Task => ({
          id: taskId,
          title: title || `Task ${taskId}`,
          description: description || '',
          status,
          tags: ['agent'],
          assignee: 'BigBrain',
          priority: 'medium',
          createdAt: Date.now(),
        });
        switch (activity.type) {
          case 'task.received': {
            if (existing) return state;
            const task = ensure(
              'todo',
              (d.description || `Task ${taskId}`).slice(0, 60),
              `${d.subtasks_count ?? '?'} subtask(s)`
            );
            return { tasks: [...state.tasks, task] };
          }
          case 'subtask.started': {
            const desc = `${d.brain || 'brain'}: ${(d.description || '').slice(0, 80)}`;
            if (existing) {
              return {
                tasks: state.tasks.map((t) =>
                  t.id === taskId ? { ...t, status: 'in-progress', description: desc } : t
                ),
              };
            }
            return { tasks: [...state.tasks, ensure('in-progress', undefined, desc)] };
          }
          case 'subtask.complete': {
            return state; // task stays in-progress until task.complete
          }
          case 'task.complete': {
            if (existing) {
              return {
                tasks: state.tasks.map((t) => (t.id === taskId ? { ...t, status: 'done' } : t)),
              };
            }
            return { tasks: [...state.tasks, ensure('done')] };
          }
          case 'task.failed': {
            if (existing) {
              return {
                tasks: state.tasks.map((t) =>
                  t.id === taskId
                    ? { ...t, status: 'review', tags: [...new Set([...t.tags, 'failed'])] }
                    : t
                ),
              };
            }
            return { tasks: [...state.tasks, { ...ensure('review'), tags: ['agent', 'failed'] }] };
          }
          default:
            return state;
        }
      }),
      updateTask: (id, updates) => set((state) => ({ tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)) })),
      deleteTask: (id) => set((state) => ({ tasks: state.tasks.filter((t) => t.id !== id) })),
      workspaceView: 'files',
      setWorkspaceView: (workspaceView) => set({ workspaceView }),

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
        state.connection?.send(text, state.attachments);
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
      partialize: (state) => ({ theme: state.theme, settings: state.settings, activeSessionKey: state.activeSessionKey }),
    }
  )
);
