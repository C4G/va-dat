// @vitest-environment node
import { beforeEach, expect, it, vi } from 'vitest';
const read = vi.hoisted(() => vi.fn());
vi.mock('@/lib/model-settings', () => ({ readModelSettings: read }));
import { GET } from './route';
beforeEach(() => {
  read.mockReset();
});
it('returns only enabled models without a session or cache', async () => {
  read.mockResolvedValue({
    enabledModelIds: ['gpt-4o'],
    defaultModelId: 'gpt-4o',
  });
  const response = await GET();
  expect(response.status).toBe(200);
  expect(response.headers.get('cache-control')).toBe('no-store');
  const data = await response.json();
  expect(data.models.map((model: { id: string }) => model.id)).toEqual([
    'gpt-4o',
  ]);
  expect(data.defaultModelId).toBe('gpt-4o');
});
it('does not fall back to the full catalog during a database outage', async () => {
  read.mockRejectedValue(new Error('database offline'));
  expect((await GET()).status).toBe(503);
});
