const API_BASE = '';

async function fetchWithCredentials(url: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, {
    ...options,
    credentials: 'same-origin',
    headers: {
      ...options.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response;
}

export const authApi = {
  async login(token: string): Promise<void> {
    await fetchWithCredentials(`${API_BASE}/api/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
  },

  async me(): Promise<{ name: string; email: string }> {
    const response = await fetchWithCredentials(`${API_BASE}/api/v2/auth/me`);
    return response.json();
  },

  async logout(): Promise<void> {
    await fetchWithCredentials(`${API_BASE}/api/logout`, { method: 'POST' });
  },
};

export const historyApi = {
  async get(sessionKey: string = 'default'): Promise<Message[]> {
    const response = await fetchWithCredentials(`${API_BASE}/api/history?session=${encodeURIComponent(sessionKey)}`);
    return response.json();
  },
};

export const sessionsApi = {
  async list(): Promise<Session[]> {
    const response = await fetchWithCredentials(`${API_BASE}/api/sessions`);
    return response.json();
  },
};

export const searchApi = {
  async query(q: string): Promise<Session[]> {
    const response = await fetchWithCredentials(`${API_BASE}/api/search?q=${encodeURIComponent(q)}`);
    return response.json();
  },
};

export const sendApi = {
  async message(formData: FormData): Promise<void> {
    await fetchWithCredentials(`${API_BASE}/api/send`, {
      method: 'POST',
      body: formData,
    });
  },
};

export const ttsApi = {
  async speak(text: string): Promise<Blob> {
    const response = await fetchWithCredentials(`${API_BASE}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    return response.blob();
  },
};

export const transcribeApi = {
  async transcribe(audioBlob: Blob): Promise<{ text: string }> {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    const response = await fetchWithCredentials(`${API_BASE}/api/transcribe`, {
      method: 'POST',
      body: formData,
    });
    return response.json();
  },
};

import type { Message, Session } from '@/types';
