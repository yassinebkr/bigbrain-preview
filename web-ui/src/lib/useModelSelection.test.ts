/** The selection API preserves the requested role and reports server failures. */
import { afterEach, expect, it, vi } from 'vitest';
import { assignModelRole } from './useModelSelection';

afterEach(() => vi.unstubAllGlobals());

it.each(['front', 'planner', 'code', 'web', 'research', 'subagent'])('submits the chosen registry key for %s', async role => {
  const fetcher = vi.fn().mockResolvedValue({ ok:true, json:async () => ({ok:true}) });
  vi.stubGlobal('fetch', fetcher);
  const key = `selected-test-model-${role}`;
  await assignModelRole(role, key);
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({role, key});
});

it('propagates a rejected assignment for the settings error state', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, json:async () => ({error:'Provider unavailable'})}));
  await expect(assignModelRole('code', 'selected-test-model')).rejects.toThrow('Provider unavailable');
});
