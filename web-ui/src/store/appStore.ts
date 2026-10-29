import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Message, Attachment, Session, Settings, Theme, View, ConnectionStatus, SidebarPanel, User, CanvasOp, Task } from '@/types';
import type { ConnectionLike } from '@/lib/connection';
import { parseWidgetProposal, type WidgetProposal } from '@/lib/widgetPolicy';
import { researchUpdate, type ResearchView } from '@/lib/research';

// A first message can arrive before sessions.create answers. Never send it
// with the previous conversation's id (or the server's implicit fallback).
let pendingSession: Promise<string> | null = null;
let sessionGeneration = 0;
let cancelledSends = 0;
const fileProgressLabels: Record<string, string> = {
  writing_file: 'Création du fichier', writing_web_file: 'Création du fichier',
  file_written: 'Fichier enregistré', editing_file: 'Modification du fichier',
  maintenance_list: 'Exploration du projet', maintenance_search: 'Recherche dans le projet',
  maintenance_read: 'Lecture du fichier', maintenance_diagnose: 'Diagnostic du projet',
  maintenance_patch: 'Correction ciblée', maintenance_verify: 'Vérification du projet',
  maintenance_prepare_environment: 'Préparation des outils du projet',
  maintenance_diagnostic_read: 'Analyse des diagnostics', maintenance_entry_point: 'Point d’entrée',
  maintenance_arbitrate: 'Décision nécessaire',
};

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
  researches?: Record<string, ResearchView>;
  widgetProposal?: WidgetProposal;
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
  localProject?: { project_id: string; revision: number };
  entryPoint?: string;
  deliverableType?: string;
  previewUrl?: string;
  runnable?: boolean;
  deliveryStatus?: 'ready' | 'incomplete';
  awaitingApproval?: boolean;
  resultKind?: string;
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
  historyError: string | null;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  clearMessages: () => void;
  setMessages: (messages: Message[]) => void;
  restoreSessionHistory: (sessionId: string, messages: Message[], asOf?: number) => void;

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
  sessionRuns: Record<string, RunState>;
  runsById: Record<string, RunState>;
  selectRun: (id: string) => void;
  // Finished runs are timeline records, grouped by their chat session.
  completedRuns: RunState[];
  applyRunEvent: (activity: Omit<AgentActivity, 'ts'> & { ts?: number }) => void;
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
  contractProposal: { designId: string; planId: string; request: string; contracts: string[]; target?: { mode: string; path: string };
    sourceTransmission?: { project_id: string; revision: number; recipient: { provider: string; endpoint: string };
      source_versions: Record<string, string>; source_bytes: number; excluded_paths: string[] } } | null;
  sessionProposals: Record<string, NonNullable<AppState['contractProposal']>>;
  contractSending: boolean;
  contractError: string | null;
  setContractProposal: (
    proposal: NonNullable<AppState['contractProposal']> | null
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
  forgetSession: (key: string) => void;
  renameSession: (key: string, title: string) => Promise<void>;
  deleteSession: (key: string) => Promise<void>;

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
      setView: (view) => {
        if (view === 'welcome') get().startNewSession();
        else set({ view });
      },

      // Messages
      // Chat history is owned by the selected server session, not a global
      // localStorage transcript left over from another conversation.
      messages: [],
      historyError: null,
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
      restoreSessionHistory: (sessionId, messages, asOf) => set((state) => {
        if (sessionId !== state.activeSessionKey) return {};
        const later = state.messages.filter((message) => (message.role === 'user' && message.id.startsWith('user-') || !asOf || message.timestamp > asOf) &&
          !messages.some((old) => old.role === message.role && old.content === message.content));
        return { messages: [...messages, ...later], historyError: null };
      }),

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
      setConnection: (connection) => {
        connection?.switchSession(get().activeSessionKey);
        set({ connection });
      },

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
      sessionRuns: {},
      runsById: {},
      selectRun: (id) => set((state) => {
        const run = state.runsById[id];
        if (!run) return {};
        return { sessionRuns: { ...state.sessionRuns, [run.sessionId]: run },
          ...(run.sessionId === state.activeSessionKey ? { activeRun: run } : {}) };
      }),
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
      sessionProposals: {},
      contractSending: false,
      contractError: null,
      setContractProposal: (proposal) => set((state) => {
        const sessionProposals = { ...state.sessionProposals };
        if (proposal) sessionProposals[state.activeSessionKey] = proposal;
        else delete sessionProposals[state.activeSessionKey];
        return { sessionProposals, contractProposal: proposal, contractSending: false, contractError: null };
      }),
      sendContractDecision: async (approve) => {
        const proposal = get().contractProposal;
        if (!proposal || get().contractSending) return;
        set({ contractSending: true, contractError: null });
        try {
          const r = await fetch('/api/contracts/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              design_id: proposal.designId,
              plan_id: proposal.planId,
              approve,
            }),
            signal: AbortSignal.timeout(15000),
          });
          if (get().contractProposal?.planId !== proposal.planId) return;
          if (r.ok) {
            // HTTP only acknowledges delivery; only the recorded bus
            // verdict resolves the card. Failed persistence must stay visible.
            set({ contractSending: false });
          } else {
            set({ contractSending: false, contractError: 'Décision non enregistrée. Tu peux réessayer.' });
          }
        } catch {
          if (get().contractProposal?.planId === proposal.planId) {
            set({ contractSending: false, contractError: 'Confirmation impossible. Le contrat reste en attente.' });
          }
        }
      },

      // Fold bus events into the current run. Pure state machine:
      // task.routing opens a run immediately; subtask.* upsert steps;
      // workspace.file_written collects files; task.complete/failed
      // docks the finished record into its conversation timeline.
      applyRunEvent: (activity) => set((state) => {
        const d = activity.detail || {};
        const sessionRuns = { ...state.sessionRuns };
        if (state.activeRun && !sessionRuns[state.activeRun.sessionId]) {
          sessionRuns[state.activeRun.sessionId] = state.activeRun;
        }
        const runsById = { ...state.runsById };
        for (const legacy of Object.values(sessionRuns)) runsById[legacy.id] ||= legacy;
        const taskId = d.task_id || d.plan_id;
        const byTask = taskId ? runsById[taskId] : null;
        const finished = taskId ? state.completedRuns.find((r) => r.id === taskId) : null;
        const terminal = ['task.complete', 'task.failed', 'task.cancelled'].includes(activity.type);
        const sessionId = String(d.session_id || byTask?.sessionId || finished?.sessionId || state.activeRun?.sessionId || state.activeSessionKey);
        if (activity.type === 'task.routing' && taskId) {
          // Migrate pre-correlation cached placeholders during journal catch-up.
          // Real runs now use a stable UUID, never this legacy prefix.
          for (const legacy of Object.values(runsById)) {
            if (legacy.sessionId === sessionId && legacy.id.startsWith('routing-')) {
              delete runsById[legacy.id];
              if (sessionRuns[sessionId]?.id === legacy.id) delete sessionRuns[sessionId];
            }
          }
        }
        const pendingRouting = Object.values(runsById).find((r) => r.sessionId === sessionId && r.id.startsWith('routing-'));
        const run = byTask || (terminal ? finished : null) || (activity.type === 'task.received' ? pendingRouting :
          !taskId ? sessionRuns[sessionId] : null) || null;
        // Replays/snapshots are idempotent. A finished run never becomes live again.
        if (finished && activity.type === 'task.progress') {
          if (d.research && d.subtask_id && d.session_id === finished.sessionId && d.task_id === finished.id) {
            const key = `${d.subtask_id}:${d.research.research_id}`;
            const research = researchUpdate(d.research, finished.researches?.[key], d.observation, d);
            if (!research) return {};
            return { completedRuns: state.completedRuns.map((item) => item.id === finished.id
              ? { ...item, researches: { ...item.researches, [key]: research } } : item) };
          }
          const path = typeof d.path === 'string' ? d.path : typeof d.file_path === 'string' ? d.file_path : '';
          const label = fileProgressLabels[d.stage];
          if (path && label) return { completedRuns: state.completedRuns.map((item) => item.id === finished.id
            ? { ...item, steps: item.steps.map((step) => step.id === d.subtask_id
              ? { ...step, description: `${label} · ${path}` } : step) } : item) };
        }
        if (finished && !terminal) {
          if (activity.type === 'contracts.proposal' && typeof d.project_target?.path === 'string') {
            return { completedRuns: state.completedRuns.map((item) => item.id === finished.id
              ? { ...item, projectPath: d.project_target.path } : item) };
          }
          delete runsById[finished.id];
          if (sessionRuns[sessionId] && !runsById[sessionRuns[sessionId].id]) delete sessionRuns[sessionId];
          const sessionProposals = { ...state.sessionProposals };
          if (sessionProposals[sessionId]?.planId === taskId) delete sessionProposals[sessionId];
          return { runsById, sessionRuns, sessionProposals,
            activeRun: sessionRuns[state.activeSessionKey] || null,
            contractProposal: sessionProposals[state.activeSessionKey] || null };
        }
        const reduce = (): Partial<AppState> => {
        const opensRun = ['task.routing', 'task.received', 'contracts.proposal'].includes(activity.type);
        if (run && !opensRun) {
          if (d.session_id && d.session_id !== run.sessionId) return {};
          if (d.task_id && d.task_id !== run.id && !run.id.startsWith('routing-')) return {};
        }
        switch (activity.type) {
          case 'workspace.proposal': {
            if (!run || run.status !== 'running' || !d.session_id || !d.task_id
                || d.session_id !== run.sessionId || d.task_id !== run.id || d.producer !== 'architect') return {};
            const proposal = parseWidgetProposal(d.proposal);
            if (!proposal || proposal.revision <= (run.widgetProposal?.revision || 0)) return {};
            return { activeRun: { ...run, widgetProposal: proposal } };
          }
          case 'planning.stage': {
            if (!run || run.status !== 'running') return {};
            const id = `planning-${d.stage}`;
            const step: RunStep = { id, brain: 'planner', description: String(d.description || d.stage),
              status: d.status === 'done' ? 'done' : d.status === 'failed' ? 'failed' : 'running',
              durationMs: typeof d.elapsed_ms === 'number' ? d.elapsed_ms : undefined };
            return { activeRun: { ...run, steps: [...run.steps.filter((s) => s.id !== id), step] } };
          }
          case 'task.routing': {
            if (byTask) return {};
            const sessionId = String(d.session_id || state.activeSessionKey || '');
            const fresh: RunState = {
              sessionId,
              id: d.task_id || `routing-${Date.now()}`,
              description: String(d.description || 'Preparing task'),
              projectPath: typeof d.project_path === 'string' ? d.project_path : undefined,
              status: 'running',
              startedAt: activity.ts || Date.now(),
              steps: [],
              files: [],
            };
            return { activeRun: fresh, runPanelDismissed: false };
          }
          case 'task.received': {
            if (run && run.id === d.task_id) return { activeRun: { ...run,
              projectPath: typeof d.project_path === 'string' ? d.project_path : run.projectPath } };
            const previous = run?.sessionId === d.session_id ? run : null;
            const fresh: RunState = {
              sessionId: String(d.session_id || run?.sessionId || state.activeSessionKey || ''),
              id: d.task_id || `run-${Date.now()}`,
              description: String(d.description || 'Task'),
              projectPath: typeof d.project_path === 'string' ? d.project_path : previous?.projectPath,
              status: 'running',
              startedAt: previous?.startedAt || activity.ts || Date.now(),
              steps: previous?.steps.filter((s) => s.id.startsWith('planning-')) || [],
              files: [],
            };
            return { activeRun: fresh, runPanelDismissed: false };
          }
          case 'contracts.proposal': {
            const sessionId = String(d.session_id || run?.sessionId || state.activeSessionKey || '');
            if (run && run.status === 'running' && run.sessionId === sessionId) {
              return { activeRun: { ...run, sessionId, awaitingApproval: true,
                projectPath: typeof d.project_target?.path === 'string' ? d.project_target.path : run.projectPath }, runPanelDismissed: false };
            }
            const fresh: RunState = {
              sessionId,
              id: String(d.plan_id || `approval-${Date.now()}`),
              description: String(d.user_request || 'Awaiting contract approval'),
              status: 'running',
              awaitingApproval: true,
              startedAt: activity.ts || Date.now(),
              steps: [],
              files: [],
            };
            return { activeRun: fresh, runPanelDismissed: false };
          }
          case 'contracts.approved':
          case 'contracts.rejected': {
            return run ? { activeRun: { ...run, awaitingApproval: false } } : {};
          }
          case 'subtask.started': {
            if (!run || run.status !== 'running') return {};
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
            if (!run || run.status !== 'running') return {};
            const delta = String(d.delta || '');
            if (!delta) return {};
            const targetId = d.subtask_id
              ? String(d.subtask_id)
              : (run.steps.find((s) => s.status === 'running')?.id || null);
            if (!targetId) return {};
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
          case 'task.progress': {
            if (!run) return {};
            if (d.research) {
              if (!d.subtask_id || d.session_id !== run.sessionId || d.task_id !== run.id) return {};
              const key = `${d.subtask_id}:${d.research.research_id}`;
              const research = researchUpdate(d.research, run.researches?.[key], d.observation, d);
              return research ? { activeRun: { ...run, researches: { ...run.researches, [key]: research } } } : {};
            }
            const labels: Record<string, string> = {
              ...fileProgressLabels,
              creating_venv: 'Préparation de l’environnement Python', installing_deps: 'Installation des dépendances',
              install_warning: 'Installation à vérifier', syntax_error: 'Correction de la syntaxe',
              batch_write_start: 'Création des fichiers', batch_write_complete: 'Fichiers enregistrés',
              diff_failed_fallback: 'Reprise de la modification', searching: 'Recherche',
              assembling: 'Assemblage du projet', running: 'Exécution du projet', executing: 'Exécution',
              generating_code: 'Génération du code', retrying: 'Correction en cours',
              completed: 'Étape terminée', succeeded: 'Exécution réussie', failed_after_retries: 'Correction non aboutie',
              starting_server: 'Démarrage du serveur', server_running: 'Serveur disponible', server_failed: 'Démarrage impossible',
              web_build: 'Compilation de l’application', web_build_repair: 'Correction de la compilation',
              browser_testing: 'Tests navigateur', browser_repair: 'Correction après test', preview_ready: 'Aperçu prêt',
            };
            const label = labels[d.stage];
            if (!label) return {};
            const retry = typeof d.attempt === 'number' && Number.isInteger(d.attempt) && d.attempt > 1
              ? ` · tentative ${d.attempt}` : '';
            const path = typeof d.path === 'string' ? d.path : typeof d.file_path === 'string' ? d.file_path : '';
            return { activeRun: { ...run, steps: run.steps.map((step) => step.id === d.subtask_id
              ? { ...step, description: `${label}${path ? ` · ${path}` : ''}${retry}` }
              : step) } };
          }
          case 'subtask.complete':
          case 'subtask.failed': {
            if (!run || run.status !== 'running') return {};
            const id = String(d.subtask_id || `step-${run.steps.length}`);
            const failed = activity.type === 'subtask.failed';
            const durationMs = typeof d.execution_time === 'number' ? d.execution_time * 1000 : undefined;
            const exists = run.steps.some((s) => s.id === id);
            const steps = exists
              ? run.steps.map((s) =>
                  s.id === id ? { ...s, status: failed ? ('failed' as const) : ('done' as const), durationMs } : s
                )
              : [...run.steps, { id, brain: d.brain, description: String(d.description || 'subtask'),
                  status: failed ? ('failed' as const) : ('done' as const), durationMs }];
            return { activeRun: { ...run, steps } };
          }
          case 'workspace.file_written': {
            if (!run || run.status !== 'running' || !d.path) return {};
            const path = String(d.path);
            if (run.files.some((f) => f.path === path)) return {};
            return { activeRun: { ...run, files: [...run.files, { path, ts: Date.now() }] } };
          }
          case 'verification.run_recorded': {
            // Harness P4: the gate's verdict per attempt, attached to the
            // live run. An orphan event (no active run) is dropped.
            if (!run) return {};
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
            if (!run) return {};
            const status: RunState['status'] =
              d.delivery_status === 'incomplete' ? 'failed' : activity.type === 'task.complete' ? 'done'
              : activity.type === 'task.cancelled' ? 'cancelled'
              : 'failed';
            return {
              activeRun: null,
              completedRuns: [...state.completedRuns.filter((item) => item.id !== run.id), {
                ...run,
                status,
                steps: run.steps.map((step) => status === 'failed' && step.status === 'running'
                  ? { ...step, status: 'failed' as const } : step),
                awaitingApproval: false,
                finishedAt: activity.ts || run.finishedAt || Date.now(),
                error: d.error ? String(d.error).slice(0, 200) : run.error,
                projectName: d.project_name ? String(d.project_name) : run.projectName,
                projectPath: d.project_path ? String(d.project_path) : run.projectPath,
                entryPoint: d.entry_point ? String(d.entry_point) : run.entryPoint,
                deliverableType: d.deliverable_type ? String(d.deliverable_type) : run.deliverableType,
                previewUrl: d.preview_url ? String(d.preview_url) : run.previewUrl,
                runnable: d.delivery_status === 'incomplete' ? false : typeof d.runnable === 'boolean' ? d.runnable : run.runnable,
                deliveryStatus: d.delivery_status === 'ready' || d.delivery_status === 'incomplete' ? d.delivery_status : run.deliveryStatus,
                resultKind: d.result_kind || run.resultKind,
              }].slice(-100),
            };
          }
          default:
            return {};
        }
        };
        const update = reduce();
        const localProject = d.local_project;
        if (localProject && typeof localProject.project_id === 'string' && Number.isInteger(localProject.revision)) {
          if (update.activeRun) update.activeRun = { ...update.activeRun, localProject, projectPath: undefined };
          if (update.completedRuns) update.completedRuns = update.completedRuns.map(item => item.id === taskId
            ? { ...item, localProject, projectPath: undefined } : item);
        }
        if ('activeRun' in update) {
          if (run && run.id !== update.activeRun?.id) delete runsById[run.id];
          if (update.activeRun) runsById[update.activeRun.id] = update.activeRun;
          else if (taskId) delete runsById[taskId];
          const remaining = Object.values(runsById).filter((r) => r.sessionId === sessionId);
          // Keep the user's visible project stable while a quick side-task runs.
          const selected = sessionRuns[sessionId];
          const preferred = selected && runsById[selected.id] || remaining[0];
          if (preferred) sessionRuns[sessionId] = preferred;
          else delete sessionRuns[sessionId];
          // A background conversation updates its record, never the visible
          // conversation's active run (including when that conversation is empty).
          update.activeRun = sessionRuns[state.activeSessionKey] || null;
        }
        const sessionProposals = { ...state.sessionProposals };
        if (activity.type === 'contracts.proposal' && d.design_id && d.plan_id) {
          sessionProposals[sessionId] = { designId: d.design_id, planId: d.plan_id,
            request: d.user_request || '', contracts: Array.isArray(d.contracts) ? d.contracts : [],
            ...(d.source_transmission ? { sourceTransmission: d.source_transmission } : {}),
            ...(d.project_target ? { target: d.project_target } : {}) };
        } else if (['contracts.approved', 'contracts.rejected', 'task.cancelled', 'task.failed', 'task.complete'].includes(activity.type)) {
          const proposal = sessionProposals[sessionId];
          const target = d.plan_id || d.task_id;
          if (!target || proposal?.planId === target) delete sessionProposals[sessionId];
        }
        return { ...update, runsById, sessionRuns, sessionProposals,
          contractProposal: sessionProposals[state.activeSessionKey] || null,
          ...(!sessionProposals[state.activeSessionKey] ? { contractSending: false, contractError: null } : {}) };
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
      renameSession: async (key, title) => {
        const connection = get().connection;
        if (!connection?.renameSession) throw new Error('Renommage indisponible sur cette connexion.');
        await connection.renameSession(key, title);
        set((s) => ({ sessions: s.sessions.map((session) => session.key === key ? { ...session, title: title.trim() } : session) }));
        get().refreshSessions();
      },
      deleteSession: async (key) => {
        const connection = get().connection;
        if (!connection?.deleteSession) throw new Error('Suppression indisponible sur cette connexion.');
        await connection.deleteSession(key);
        get().forgetSession(key);
        get().refreshSessions();
      },
      forgetSession: (key) => {
        if (get().activeSessionKey === key) {
          get().switchSession('');
          set({ inputText: '', attachments: [], activeRun: null, canvasOps: [], historyError: null });
          localStorage.removeItem('aplot_messages');
        }
        set((s) => ({ sessions: s.sessions.filter((session) => session.key !== key),
          runsById: Object.fromEntries(Object.entries(s.runsById).filter(([, run]) => run.sessionId !== key)),
          completedRuns: s.completedRuns.filter((run) => run.sessionId !== key),
          sessionRuns: Object.fromEntries(Object.entries(s.sessionRuns).filter(([id]) => id !== key)),
          sessionProposals: Object.fromEntries(Object.entries(s.sessionProposals).filter(([id]) => id !== key)),
          agentActivities: s.agentActivities.filter((activity) => activity.detail?.session_id !== key),
        }));
        void import('./workspaceStore').then(({ useWorkspaceStore }) => useWorkspaceStore.getState().forgetSession(key));
        void import('./projectRunStore').then(({ useProjectRunStore }) => {
          const ids = Object.entries(useProjectRunStore.getState().launches).filter(([id]) => {
            try { return JSON.parse(id)[0] === key; } catch { return false; }
          }).map(([, launch]) => launch.runId);
          set((s) => ({ liveRuns: Object.fromEntries(Object.entries(s.liveRuns).filter(([id]) => !ids.includes(id))) }));
          useProjectRunStore.getState().forgetSession(key);
        });
      },
      activeSessionKey: '',
      setSessions: (sessions) => set({ sessions }),
      setActiveSessionKey: (activeSessionKey) => {
        get().connection?.switchSession(activeSessionKey);
        set({ activeSessionKey });
      },
      switchSession: (key) => {
        sessionGeneration += 1;
        pendingSession = null;
        get().connection?.switchSession(key);
        // A run belongs to its conversation — the record of the previous
        // one must not follow the user into the next.
        set({ activeSessionKey: key, messages: [], view: 'welcome',
              streamingText: '', isStreaming: false, contractProposal: null,
              contractSending: false, contractError: null,
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
        conn?.switchSession('');
        const generation = ++sessionGeneration;
        set({ activeSessionKey: '', messages: [], view: 'welcome',
              streamingText: '', isStreaming: false, contractProposal: null,
              contractSending: false, inputText: '', attachments: [],
              contractError: null,
              runPanelDismissed: false });
        if (conn?.createSession) {
          let resolveSession!: (id: string) => void;
          pendingSession = new Promise((resolve) => { resolveSession = resolve; });
          conn.createSession((session) => {
            resolveSession(session?.id || '');
            if (!session?.id || generation !== sessionGeneration) return;
            pendingSession = null;
            conn.switchSession(session.id);
            set({ activeSessionKey: session.id });
            get().refreshSessions();
          });
        } else {
          pendingSession = null;
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
        sessionGeneration += 1;
        pendingSession = null;
        get().connection?.switchSession(key);
        set({
          activeSessionKey: key,
          historyError: null,
          sidebarPanel: null,
          messages: [],
          streamingText: '',
          isStreaming: false,
          contractProposal: get().sessionProposals[key] || null,
          contractSending: false, contractError: null,
          runPanelDismissed: false,
        });
        get().connection?.loadHistory((frame: any) => {
          if (get().activeSessionKey !== key) return;
          if (frame?.ok && frame.payload?.messages) {
            get().restoreSessionHistory(key, frame.payload.messages.map((m: any) => ({
                id: m.id || `hist-${Date.now()}-${Math.random()}`,
                role: m.role === 'user' ? 'user' : 'assistant',
                content: m.content,
                timestamp: m.timestamp
                  ? (m.timestamp < 1e12 ? m.timestamp * 1000 : m.timestamp)
                  : Date.now(),
              })), frame.payload.asOf);
            set({ view: 'chat' });
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
        if (!state.connection || state.connectionStatus !== 'connected') {
          set({ historyError: 'Connexion au serveur indisponible. Votre message est conservé dans le champ de saisie.', isStreaming: false });
          return;
        }
        const userMessage: Message = { id: `user-${Date.now()}`, role: 'user', content: text, timestamp: Date.now(), attachments: state.attachments.length > 0 ? [...state.attachments] : undefined };
        // Sending from the home page ALWAYS starts a new conversation —
        // the previous transcript must not bleed into it.
        const isNewConversation = state.view === 'welcome';
        // Also migrate a persisted/home view from older versions, which
        // could still point at a conversation containing messages/runs.
        if (isNewConversation && (state.messages.length > 0
            || !!selectSessionRun(state)
            || state.completedRuns.some((r) => r.sessionId === state.activeSessionKey))) {
          get().startNewSession();
        }
        const sessionReady = pendingSession;
        const sessionKey = get().activeSessionKey;
        const cancellation = cancelledSends;
        set((s) => ({
          messages: isNewConversation ? [userMessage] : [...s.messages, userMessage],
          inputText: '',
          attachments: [],
          view: 'chat',
          historyError: null,
          isStreaming: true,
          streamingText: '',
        }));
        // Attachments: upload the files first (POST /api/attachments),
        // then send the message with server refs — the front brain
        // records them in persistent memory. Offline: the message goes
        // out without the files (upload failure never blocks the text).
        (async () => {
          const targetSession = sessionReady ? await sessionReady : sessionKey;
          if (cancellation !== cancelledSends) return;
          if (sessionReady && !targetSession) {
            set({ isStreaming: false });
            return;
          }
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
          if (cancellation !== cancelledSends) return;
          state.connection?.send(text, refs,
                                  targetSession || undefined, state.currentProject);
        })();
      },

      // Stop button: cancel server-side (front brain stream + orchestrated
      // run), then close the streaming bubble locally with whatever text
      // already arrived (finalizeStreaming keeps it as a message).
      stopGeneration: () => {
        cancelledSends += 1;
        get().connection?.cancel?.();
        get().finalizeStreaming();
        const sessionId = get().activeSessionKey;
        const runs = Object.values(get().runsById).filter((r) => r.sessionId === sessionId);
        const legacy = selectSessionRun(get());
        if (legacy && !runs.some((r) => r.id === legacy.id)) runs.push(legacy);
        for (const run of runs) get().applyRunEvent({ type: 'task.cancelled', detail: {
          session_id: sessionId, task_id: run.id,
        } });
        set({ contractProposal: null, contractSending: false });
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
        sessionRuns: state.sessionRuns,
        runsById: state.runsById,
        sessionProposals: state.sessionProposals,
        completedRuns: state.completedRuns,
        // Layout persistence: where the user was working (view + workspace
        // tab + the open code file) survives a reload.
        view: state.view,
        workspaceView: state.workspaceView,
        viewerFilePath: state.viewerFilePath,
        dismissedNudges: state.dismissedNudges,
        // Only completed manual execution records are restored as results.
        // An interrupted WS subscription must not become a fictional success.
        liveRuns: Object.fromEntries(Object.entries(state.liveRuns).filter(([, run]) => run.done).slice(-30)),
      }),
    }
  )
);

export function selectSessionRun(state: Pick<AppState, 'activeSessionKey' | 'sessionRuns' | 'activeRun'>) {
  return state.sessionRuns[state.activeSessionKey]
    || (state.activeRun?.sessionId === state.activeSessionKey ? state.activeRun : null);
}
