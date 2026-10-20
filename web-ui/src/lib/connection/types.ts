// Shared connection contract — the interface between an adapter and the app.
// Both adapters (scratchy, bigbrain) must satisfy it; the store and App
// depend only on this.

export interface ConnectionCallbacks {
  onMessage?: (message: { text: string; role: string; timestamp: string; source: string }) => void;
  onStreamDelta?: (message: { text: string; role: string; source: string }) => void;
  onStatusChange?: (status: string) => void;
  onAgentActivity?: (activity: { type: string; phase?: string; name?: string; detail?: any; ts?: number }) => void;
  onQueueDrained?: () => void;
  onQueueReplay?: (msg: { text: string; id: string; ts: number }) => void;
  onSendError?: (error: { message: string }, messageId?: string) => void;
  onMessageStatus?: (messageId: string, status: string) => void;
  onCanvasUpdate?: (payload: any) => void;
  onUserInfo?: (user: any) => void;
  onReconnected?: () => void;
  onRemoteUserMessage?: (message: any) => void;
  onResumeCatchUp?: (messages: any[], sessionId?: string, asOf?: number) => void;
  onHistoryError?: (error: string, sessionId?: string) => void;
  onRunEnd?: () => void;
  onSessionChanged?: (change: { sessionId: string; deleted?: boolean; title?: string }) => void;
}

/**
 * Public surface every adapter must expose (mirrors the original Scratchy
 * Connection class used by the store and App.tsx).
 */
export interface SessionSummary {
  id: string;
  title: string;
  updated_at: number;
  message_count: number;
}

export interface ConnectionLike {
  sessionKey: string;
  on<K extends keyof ConnectionCallbacks>(event: K, callback: ConnectionCallbacks[K]): void;
  connect(): void;
  disconnect(): void;
  send(text: string, attachments?: any[], sessionId?: string, navigationProject?: string | null): string;
  cancel?(): void;
  loadHistory(callback?: (frame: any) => void, sessionId?: string): void;
  listSessions?(callback: (sessions: SessionSummary[]) => void): void;
  createSession?(callback: (session: SessionSummary) => void): void;
  deleteSession?(sessionId: string): Promise<void>;
  renameSession?(sessionId: string, title: string): Promise<void>;
  switchSession(newSessionKey: string): void;
  forceReconnect(): void;
  checkHealth(callback: (alive: boolean) => void, timeoutMs?: number): void;
}
