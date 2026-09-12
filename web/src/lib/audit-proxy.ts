import http from 'node:http';
import https from 'node:https';
import { Readable } from 'node:stream';
import { readModelSettings } from '@/lib/model-settings';

type AuditPath =
  | '/api/audit'
  | '/api/audit/url'
  | '/api/audit/url/nested'
  | '/api/validate-key';

// Node's socket timeout measures inactivity, not the total audit duration.
export function forwardJson(
  request: Request,
  path: AuditPath,
  data: Record<string, unknown>
): Promise<Response> {
  const target = new URL(
    path,
    process.env.PYTHON_API_URL || 'http://127.0.0.1:8000'
  );
  const payload = Buffer.from(JSON.stringify(data));
  return new Promise((resolve, reject) => {
    const transport = target.protocol === 'https:' ? https : http;
    const upstream = transport.request(
      target,
      {
        method: 'POST',
        signal: request.signal,
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': payload.byteLength,
        },
      },
      (response) => {
        resolve(
          new Response(Readable.toWeb(response) as ReadableStream<Uint8Array>, {
            status: response.statusCode || 502,
            headers: {
              'Content-Type':
                response.headers['content-type'] || 'application/json',
              'Cache-Control': 'no-store, no-transform',
              'X-Accel-Buffering': 'no',
            },
          })
        );
      }
    );
    upstream.setTimeout(600_000, () =>
      upstream.destroy(new Error('Audit service timed out.'))
    );
    upstream.on('error', reject);
    upstream.end(payload);
  });
}

export async function proxyAudit(request: Request, path: AuditPath) {
  let data: Record<string, unknown>;
  try {
    data = await request.json();
    if (!data || typeof data !== 'object' || Array.isArray(data))
      throw new Error();
    for (const key of [
      'model',
      'html_content',
      'url',
      'api_key',
      'openai_api_key',
      'gemini_api_key',
      'provider',
    ]) {
      if (data[key] !== undefined && typeof data[key] !== 'string')
        throw new Error();
    }
  } catch {
    return Response.json(
      { success: false, error: 'Invalid JSON request.' },
      { status: 400 }
    );
  }
  if (path !== '/api/validate-key') {
    let settings;
    try {
      settings = await readModelSettings();
    } catch {
      return Response.json(
        { success: false, error: 'Model configuration is unavailable.' },
        { status: 503 }
      );
    }
    const model = data.model ?? settings.defaultModelId;
    if (
      typeof model !== 'string' ||
      !settings.enabledModelIds.includes(model)
    ) {
      return Response.json(
        {
          success: false,
          error: 'This model is unavailable. Reload the model list.',
        },
        { status: 400 }
      );
    }
    data.model = model;
  } else if (
    !['anthropic', 'openai', 'gemini'].includes(
      String(data.provider ?? 'anthropic')
    )
  ) {
    return Response.json(
      { success: false, error: 'Unsupported provider.' },
      { status: 400 }
    );
  }
  try {
    return await forwardJson(request, path, data);
  } catch {
    return Response.json(
      {
        success: false,
        error: 'The audit service is unavailable or timed out. Try again.',
      },
      { status: 502 }
    );
  }
}
