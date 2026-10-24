import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { startCodexLogin } from './codexLogin';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function callbacks() {
  return { request: vi.fn(), open: vi.fn().mockReturnValue(null), status: vi.fn(), link: vi.fn(), connected: vi.fn() };
}

it('opens the returned URL in the user browser and confirms ChatGPT login', async () => {
  const c = callbacks();
  const popup = { opener: {}, location: { href: 'about:blank' }, closed: false, close: vi.fn() };
  c.open.mockReturnValue(popup);
  c.request.mockResolvedValueOnce({ authUrl: 'https://auth.openai.com/login' })
    .mockResolvedValueOnce({ authenticated: true, type: 'chatgpt' });
  const flow = startCodexLogin(c);
  expect(c.open).toHaveBeenCalledOnce();
  await vi.advanceTimersByTimeAsync(3001);
  await flow.done;
  expect(popup.opener).toBeNull();
  expect(popup.location.href).toBe('https://auth.openai.com/login');
  expect(JSON.parse(c.request.mock.calls[0][1].body)).toEqual({ open_browser: false });
  expect(c.connected).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});

it('shows a clickable URL even when popup opening is blocked', async () => {
  const c = callbacks();
  c.request.mockResolvedValueOnce({ authUrl: 'https://auth.openai.com/login' })
    .mockResolvedValueOnce({ authenticated: true, type: 'chatgpt' });
  const flow = startCodexLogin(c);
  await vi.advanceTimersByTimeAsync(1);
  expect(c.link).toHaveBeenCalledWith('https://auth.openai.com/login');
  expect(c.status).toHaveBeenCalledWith(expect.stringContaining('lien'));
  await vi.advanceTimersByTimeAsync(3001);
  await flow.done;
});

it('surfaces missing CLI and polling errors without leaving a blank tab', async () => {
  const c = callbacks();
  const popup = { opener: {}, closed: false, close: vi.fn() };
  c.open.mockReturnValue(popup);
  c.request.mockRejectedValueOnce(new Error('codex CLI not found'));
  await startCodexLogin(c).done;
  expect(c.status).toHaveBeenLastCalledWith('codex CLI not found');
  expect(popup.close).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});

it('stops polling on timeout and never mistakes an API key for ChatGPT', async () => {
  const c = callbacks();
  c.request.mockResolvedValueOnce({ authUrl: 'https://auth.openai.com/login' })
    .mockResolvedValue({ authenticated: true, type: 'apiKey' });
  const flow = startCodexLogin(c, 7000);
  await vi.advanceTimersByTimeAsync(7001);
  await flow.done;
  expect(c.status).toHaveBeenLastCalledWith(expect.stringContaining('délai'));
  expect(c.connected).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});

it('cancels pending polling when the settings panel is closed', async () => {
  const c = callbacks();
  c.request.mockResolvedValue({ authUrl: 'https://auth.openai.com/login' });
  const flow = startCodexLogin(c);
  await vi.advanceTimersByTimeAsync(1);
  const calls = c.status.mock.calls.length;
  flow.stop();
  await flow.done;
  expect(c.status).toHaveBeenCalledTimes(calls);
  expect(vi.getTimerCount()).toBe(0);
});

it('rejects a non-HTTPS sign-in URL', async () => {
  const c = callbacks();
  c.request.mockResolvedValue({ authUrl: 'javascript:alert(1)' });
  await startCodexLogin(c).done;
  expect(c.status).toHaveBeenLastCalledWith('URL de connexion invalide.');
  expect(c.link).not.toHaveBeenCalledWith('javascript:alert(1)');
});
