// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({
  session: vi.fn(),
  read: vi.fn(),
  save: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ getSession: mocks.session }));
vi.mock('@/lib/model-settings', () => ({
  readModelSettings: mocks.read,
  saveModelSettings: mocks.save,
}));
import { GET, PUT } from './route';
const settings = { enabledModelIds: ['gpt-4o'], defaultModelId: 'gpt-4o' };
beforeEach(() => {
  vi.resetAllMocks();
  mocks.session.mockResolvedValue({ user: { role: 'ADMIN' } });
  mocks.read.mockResolvedValue(settings);
  mocks.save.mockResolvedValue(settings);
});
describe('admin settings authorization', () => {
  it('rejects anonymous GET and PUT', async () => {
    mocks.session.mockResolvedValue(null);
    expect((await GET()).status).toBe(401);
    expect(
      (
        await PUT(
          new Request('http://localhost/api/admin/models', {
            method: 'PUT',
            body: '{}',
          })
        )
      ).status
    ).toBe(401);
  });
  it('rejects non-admin users and ignores forged body roles', async () => {
    mocks.session.mockResolvedValue({ user: { role: 'STAFF' } });
    expect((await GET()).status).toBe(403);
    expect(
      (
        await PUT(
          new Request('http://localhost/api/admin/models', {
            method: 'PUT',
            body: JSON.stringify({ role: 'ADMIN', ...settings }),
          })
        )
      ).status
    ).toBe(403);
    expect(mocks.save).not.toHaveBeenCalled();
  });
  it('rejects cross-origin writes', async () => {
    expect(
      (
        await PUT(
          new Request('http://localhost/api/admin/models', {
            method: 'PUT',
            headers: { origin: 'https://evil.example' },
            body: JSON.stringify(settings),
          })
        )
      ).status
    ).toBe(403);
  });
  it('saves valid settings and rejects an invalid default', async () => {
    const request = (body: unknown) =>
      new Request('http://localhost/api/admin/models', {
        method: 'PUT',
        headers: { origin: 'http://localhost' },
        body: JSON.stringify(body),
      });
    expect((await PUT(request(settings))).status).toBe(200);
    expect(mocks.save).toHaveBeenCalledWith(settings);
    expect(
      (await PUT(request({ ...settings, defaultModelId: 'disabled' }))).status
    ).toBe(400);
  });
});
