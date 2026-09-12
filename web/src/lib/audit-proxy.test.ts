// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import http from 'node:http';
import { once } from 'node:events';
import { proxyAudit } from './audit-proxy';
const settings = vi.hoisted(() => vi.fn());
vi.mock('@/lib/model-settings', () => ({ readModelSettings: settings }));
const model = 'gpt-4o';
let server: http.Server | undefined;
beforeEach(() => {
  settings
    .mockReset()
    .mockResolvedValue({ enabledModelIds: [model], defaultModelId: model });
});
afterEach(async () => {
  vi.unstubAllEnvs();
  if (server) {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server!.close(() => resolve()));
    server = undefined;
  }
});
describe('audit proxy', () => {
  it('forwards UTF-8 lengths, default model, and no cookies; streams immediately', async () => {
    let finish!: () => void;
    let received: Record<string, unknown> = {};
    let headers: http.IncomingHttpHeaders = {};
    server = http.createServer((req, res) => {
      headers = req.headers;
      const chunks: Buffer[] = [];
      req.on('data', (chunk) => chunks.push(chunk));
      req.on('end', () => {
        received = JSON.parse(Buffer.concat(chunks).toString());
        res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
        res.write('{"type":"progress"}\n');
        finish = () => res.end('{"type":"result","success":true}\n');
      });
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    vi.stubEnv(
      'PYTHON_API_URL',
      `http://127.0.0.1:${(server.address() as { port: number }).port}`
    );
    const request = new Request('http://web/api/audit', {
      method: 'POST',
      headers: { cookie: 'session=secret', authorization: 'Bearer secret' },
      body: JSON.stringify({ html_content: 'café' }),
    });
    const response = await proxyAudit(request, '/api/audit');
    const reader = response.body!.getReader();
    expect(new TextDecoder().decode((await reader.read()).value)).toContain(
      'progress'
    );
    expect(received).toEqual({ html_content: 'café', model });
    expect(Number(headers['content-length'])).toBe(
      Buffer.byteLength(JSON.stringify(received))
    );
    expect(headers.cookie).toBeUndefined();
    expect(headers.authorization).toBeUndefined();
    finish();
    expect(new TextDecoder().decode((await reader.read()).value)).toContain(
      'result'
    );
    await reader.cancel();
  });
  it('rejects disabled and malformed models before forwarding', async () => {
    for (const selected of ['unknown', 42]) {
      expect(
        (
          await proxyAudit(
            new Request('http://web', {
              method: 'POST',
              body: JSON.stringify({ model: selected }),
            }),
            '/api/audit'
          )
        ).status
      ).toBe(400);
    }
  });
  it('fails closed when settings are unavailable', async () => {
    settings.mockRejectedValue(new Error('database down'));
    expect(
      (
        await proxyAudit(
          new Request('http://web', { method: 'POST', body: '{}' }),
          '/api/audit'
        )
      ).status
    ).toBe(503);
  });
  it('propagates cancellation into an active upstream stream', async () => {
    server = http.createServer((_req, res) => {
      res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
      res.write('{"type":"progress"}\n');
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    vi.stubEnv(
      'PYTHON_API_URL',
      `http://127.0.0.1:${(server.address() as { port: number }).port}`
    );
    const controller = new AbortController();
    const response = await proxyAudit(
      new Request('http://web', {
        method: 'POST',
        body: '{}',
        signal: controller.signal,
      }),
      '/api/audit'
    );
    const reader = response.body!.getReader();
    await reader.read();
    controller.abort();
    await expect(reader.read()).rejects.toThrow();
    reader.releaseLock();
  });
  it('reports upstream connection errors', async () => {
    vi.stubEnv('PYTHON_API_URL', 'http://127.0.0.1:1');
    expect(
      (
        await proxyAudit(
          new Request('http://web', { method: 'POST', body: '{}' }),
          '/api/audit'
        )
      ).status
    ).toBe(502);
  });
});
