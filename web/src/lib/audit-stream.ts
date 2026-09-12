export type AuditResult = {
  success: boolean;
  error?: string;
  summary?: Record<string, unknown>;
  programmatic_findings?: Record<string, unknown>[];
  llm_results?: Record<string, Record<string, unknown>>;
  csv_report?: string | null;
  skipped_prompts?: unknown[];
  page_results?: Record<string, AuditResult>;
  crawl_tree?: Record<string, string[]>;
  pages_audited?: string[];
};
export type ProgressEvent = {
  type: string;
  message?: string;
  stage?: string;
  [key: string]: unknown;
};

export async function readAuditResponse(
  response: Response,
  onProgress: (_event: ProgressEvent) => void
): Promise<AuditResult> {
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Audit request failed (${response.status}).`);
  }
  if (!response.headers.get('content-type')?.includes('ndjson'))
    return response.json();
  if (!response.body) throw new Error('The audit response was empty.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let result: AuditResult | undefined;
  function consume(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === 'result') {
      if (result) throw new Error('The audit returned more than one result.');
      result = event;
    } else if (event.type === 'progress') onProgress(event);
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      const lines = pending.split('\n');
      pending = lines.pop() || '';
      lines.forEach(consume);
      if (done) break;
    }
    consume(pending);
    if (!result)
      throw new Error(
        'The connection closed before the audit finished. Please try again.'
      );
    return result;
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
}
