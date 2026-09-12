// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { readAuditResponse } from './audit-stream';
describe('audit response reader', () => {
  it('handles byte-sized Unicode chunks and an unterminated final line', async () => {
    const bytes = new TextEncoder().encode(
      '{"type":"progress","message":"Checking café…"}\n{"type":"result","success":true}'
    );
    const response = new Response(
      new ReadableStream({
        start(c) {
          for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
          c.close();
        },
      }),
      { headers: { 'Content-Type': 'application/x-ndjson' } }
    );
    const progress = vi.fn();
    expect((await readAuditResponse(response, progress)).success).toBe(true);
    expect(progress).toHaveBeenCalledWith({
      type: 'progress',
      message: 'Checking café…',
    });
  });
  it('delivers progress before the final response exists', async () => {
    let stream!: ReadableStreamDefaultController;
    const response = new Response(
      new ReadableStream({
        start(c) {
          stream = c;
        },
      }),
      { headers: { 'Content-Type': 'application/x-ndjson' } }
    );
    const progress = vi.fn();
    const result = readAuditResponse(response, progress);
    stream.enqueue(
      new TextEncoder().encode('{"type":"progress","message":"Working"}\n')
    );
    await vi.waitFor(() => expect(progress).toHaveBeenCalledOnce());
    stream.enqueue(
      new TextEncoder().encode('{"type":"result","success":true}\n')
    );
    stream.close();
    expect((await result).success).toBe(true);
  });
  it('rejects a stream with no final result', async () => {
    await expect(
      readAuditResponse(
        new Response('{"type":"progress"}\n', {
          headers: { 'Content-Type': 'application/x-ndjson' },
        }),
        vi.fn()
      )
    ).rejects.toThrow('before the audit finished');
  });
  it('supports buffered JSON and HTTP errors', async () => {
    expect(
      await readAuditResponse(Response.json({ success: true }), vi.fn())
    ).toEqual({ success: true });
    await expect(
      readAuditResponse(
        Response.json({ error: 'Unavailable' }, { status: 503 }),
        vi.fn()
      )
    ).rejects.toThrow('Unavailable');
  });
});
