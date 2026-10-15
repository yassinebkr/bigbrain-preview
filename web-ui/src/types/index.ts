export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  status?: 'sending' | 'sent' | 'delivered' | 'error';
  attachments?: Attachment[];
  canvasOps?: CanvasOp[];
}

export interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  file?: File;
}

export interface Session {
  key: string;
  title: string;
  timestamp: number;
  messageCount: number;
}

export interface Settings {
  genui: boolean;
  autoSpeech: boolean;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  role?: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  token: string | null;
  user: User | null;
  error: string | null;
}

export interface CanvasOp {
  op: 'upsert' | 'patch' | 'remove' | 'clear';
  id?: string;
  type?: string;
  data?: Record<string, unknown>;
}

export type TaskStatus = 'todo' | 'in-progress' | 'review' | 'done';
export type TaskPriority = 'low' | 'medium' | 'high';

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  tags: string[];
  assignee: string;
  priority: TaskPriority;
  createdAt: number;
}

export type Theme = 'dark' | 'light';
export type View = 'welcome' | 'chat' | 'workspace' | 'discover' | 'tasks' | 'brains';
export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';
export type SidebarPanel = 'sessions' | 'settings' | null;
