'use client';
import { useEffect, useRef, useState } from 'react';
import { AuditResults } from './results';
import {
  readAuditResponse,
  type AuditResult,
  type ProgressEvent,
} from '@/lib/audit-stream';
import type { ModelOption } from '@/lib/model-catalog';

export function AuditTool() {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState('');
  const [mode, setMode] = useState('html');
  const [html, setHtml] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState('');
  const [key, setKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [keyStatus, setKeyStatus] = useState('');
  const [validating, setValidating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [result, setResult] = useState<AuditResult | null>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const errorBox = useRef<HTMLParagraphElement>(null);
  const controller = useRef<AbortController | null>(null);
  const provider = models.find((m) => m.id === model)?.provider || 'anthropic';

  async function loadModels() {
    try {
      const response = await fetch('/api/models', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setModels(data.models);
      setModel(data.defaultModelId);
      // Reloading can switch providers when an administrator changes the default.
      setKey('');
      setKeyStatus('');
      setError('');
    } catch {
      setError(
        'Could not load model options. Reload the model list to try again.'
      );
    }
  }
  useEffect(() => {
    void loadModels();
    return () => controller.current?.abort();
  }, []);
  useEffect(() => {
    if (result) resultHeading.current?.focus();
  }, [result]);
  useEffect(() => {
    if (error) errorBox.current?.focus();
  }, [error]);

  async function readFile(file?: File) {
    if (!file) return;
    if (!/\.html?$/i.test(file.name)) {
      setError('Choose an .html or .htm file.');
      return;
    }
    try {
      setHtml(await file.text());
      setFile(file);
      setError('');
    } catch {
      setError('Could not read the HTML file.');
    }
  }

  async function validateKey() {
    if (!key.trim()) {
      setKeyStatus('Enter an API key first.');
      return;
    }
    setValidating(true);
    setKeyStatus('Checking key…');
    try {
      const response = await fetch('/api/validate-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, api_key: key.trim() }),
      });
      const data = await response.json();
      setKeyStatus(
        response.ok && data.valid
          ? 'Key is valid.'
          : data.error || 'Key validation failed.'
      );
    } catch {
      setKeyStatus('Could not reach the validation service.');
    } finally {
      setValidating(false);
    }
  }

  async function run(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setResult(null);
    const content = mode === 'html' ? html.trim() : url.trim();
    if (!content) {
      setError(
        mode === 'html' ? 'Paste HTML or upload a file.' : 'Enter a URL.'
      );
      return;
    }
    setBusy(true);
    setProgress({ type: 'progress', message: 'Starting audit…' });
    controller.current = new AbortController();
    const keyField =
      provider === 'openai'
        ? 'openai_api_key'
        : provider === 'gemini'
          ? 'gemini_api_key'
          : 'api_key';
    const path =
      mode === 'html'
        ? '/api/audit'
        : mode === 'url'
          ? '/api/audit/url'
          : '/api/audit/url/nested';
    try {
      const response = await fetch(path, {
        method: 'POST',
        signal: controller.current.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          [keyField]: key.trim(),
          ...(mode === 'html' ? { html_content: content } : { url: content }),
        }),
      });
      const data = await readAuditResponse(response, setProgress);
      if (!data.success) throw new Error(data.error || 'The audit failed.');
      setResult(data);
      setProgress(null);
    } catch (err) {
      setError(
        err instanceof Error && err.name === 'AbortError'
          ? 'Stopped receiving the audit. Processing may continue briefly on the server.'
          : err instanceof Error
            ? err.message
            : 'The audit failed.'
      );
    } finally {
      setBusy(false);
    }
  }

  const providerLabel =
    provider === 'openai'
      ? 'OpenAI'
      : provider === 'gemini'
        ? 'Gemini'
        : 'Anthropic';
  const stages: Record<string, number> = {
    starting: 5,
    fetching: 8,
    fetch_complete: 12,
    crawl_complete: 15,
    programmatic_complete: 18,
    extraction_complete: 20,
    report_generating: 92,
    report_complete: 97,
  };
  let percent = stages[progress?.stage || ''] ?? 10;
  let progressDetail = '';
  if (
    progress?.stage === 'llm_progress' &&
    typeof progress.completed === 'number' &&
    typeof progress.total === 'number' &&
    progress.total > 0
  ) {
    percent = 20 + Math.round((progress.completed / progress.total) * 70);
    progressDetail = `Prompt ${progress.completed} of ${progress.total}${typeof progress.prompt_name === 'string' ? ` — ${progress.prompt_name}` : ''}`;
  } else if (
    progress?.stage === 'auditing_page' &&
    typeof progress.page === 'number' &&
    typeof progress.total_pages === 'number' &&
    progress.total_pages > 0
  ) {
    percent = Math.round((progress.page / progress.total_pages) * 90);
    progressDetail = `Page ${progress.page} of ${progress.total_pages}`;
  }
  percent = Math.max(0, Math.min(95, percent));

  return (
    <section
      id='auditTool'
      className='audit-section'
      aria-labelledby='audit-heading'
    >
      <div className='container'>
        <div className='section-header'>
          <div className='accent-bar' aria-hidden='true' />
          <h2 id='audit-heading'>Accessibility Audit Tool</h2>
          <p>
            Provide an HTML file, or enter a URL to fetch and audit — with
            optional recursive crawling of nested pages.
          </p>
        </div>
        <form onSubmit={run} className='audit-form' noValidate>
          <fieldset disabled={busy}>
            <legend className='sr-only'>Audit inputs</legend>
            <div
              className='audit-mode-group'
              role='group'
              aria-labelledby='auditModeLabel'
            >
              <p id='auditModeLabel' className='audit-mode-label'>
                Input type
              </p>
              <div className='audit-mode-tabs'>
                {[
                  ['html', 'HTML File'],
                  ['url', 'URL — Single Page'],
                  ['url-nested', 'URL — With Crawl'],
                ].map(([value, label]) => (
                  <label key={value} className='audit-mode-tab'>
                    <input
                      type='radio'
                      name='auditMode'
                      value={value}
                      checked={mode === value}
                      onChange={() => setMode(value)}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </div>
            {mode === 'html' ? (
              <div className='form-group'>
                <label htmlFor='fileInput'>
                  HTML File <span className='required-mark'>*</span>
                  <span className='sr-only'>(required)</span>
                </label>
                <div
                  className={`drop-zone ${file ? 'has-file' : ''} ${dragging ? 'drag-over' : ''}`}
                  tabIndex={busy ? -1 : 0}
                  role='group'
                  aria-label='File upload area'
                  onClick={(event) => {
                    if (!busy && !file && event.target === event.currentTarget)
                      fileInput.current?.click();
                  }}
                  onKeyDown={(event) => {
                    if (
                      event.target === event.currentTarget &&
                      !busy &&
                      (event.key === 'Enter' || event.key === ' ')
                    ) {
                      event.preventDefault();
                      fileInput.current?.click();
                    }
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (!busy) setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(event) => {
                    event.preventDefault();
                    setDragging(false);
                    if (!busy) void readFile(event.dataTransfer.files[0]);
                  }}
                >
                  <input
                    ref={fileInput}
                    id='fileInput'
                    className='file-input-hidden'
                    tabIndex={-1}
                    type='file'
                    accept='.html,.htm'
                    onChange={(event) => void readFile(event.target.files?.[0])}
                  />
                  {file ? (
                    <div>
                      <svg
                        className='drop-icon drop-icon--ok'
                        aria-hidden='true'
                        viewBox='0 0 24 24'
                        fill='none'
                        stroke='currentColor'
                        strokeWidth='1.5'
                        strokeLinecap='round'
                        strokeLinejoin='round'
                      >
                        <path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' />
                        <polyline points='14 2 14 8 20 8' />
                        <polyline points='9 15 11 17 15 13' />
                      </svg>
                      <p className='drop-filename'>{file.name}</p>
                      <p className='drop-filesize'>
                        {(file.size / 1024).toFixed(1)} KB
                      </p>
                      <button
                        type='button'
                        className='file-clear-btn'
                        aria-label='Remove file'
                        onClick={() => {
                          setFile(null);
                          setHtml('');
                          if (fileInput.current) fileInput.current.value = '';
                        }}
                      >
                        ✕ Remove
                      </button>
                    </div>
                  ) : (
                    <div
                      onClick={() => {
                        if (!busy) fileInput.current?.click();
                      }}
                    >
                      <svg
                        className='drop-icon'
                        aria-hidden='true'
                        viewBox='0 0 24 24'
                        fill='none'
                        stroke='currentColor'
                        strokeWidth='1.5'
                        strokeLinecap='round'
                        strokeLinejoin='round'
                      >
                        <path d='M12 16V4m0 0L8 8m4-4 4 4' />
                        <path d='M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2' />
                      </svg>
                      <p className='drop-label'>
                        Drag an <code>.html</code> file here
                      </p>
                      <p className='drop-hint'>
                        or{' '}
                        <button type='button' className='browse-link'>
                          click to browse
                        </button>
                      </p>
                    </div>
                  )}
                </div>
                <details className='paste-fallback'>
                  <summary>Or paste HTML directly</summary>
                  <textarea
                    rows={12}
                    placeholder='Paste the complete HTML source here…'
                    spellCheck={false}
                    autoComplete='off'
                    aria-label='Paste HTML source code'
                    value={html}
                    onChange={(event) => {
                      setHtml(event.target.value);
                      setFile(null);
                      if (fileInput.current) fileInput.current.value = '';
                    }}
                  />
                </details>
              </div>
            ) : (
              <div className='form-group'>
                <label htmlFor='urlInput'>
                  URL <span className='required-mark'>*</span>
                  <span className='sr-only'>(required)</span>
                </label>
                <input
                  id='urlInput'
                  type='url'
                  name='url'
                  placeholder='https://example.com/'
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  aria-describedby='urlHint'
                  aria-required='true'
                />
                <p id='urlHint' className='field-hint'>
                  The server fetches and audits this page. URL — With Crawl also
                  follows in-domain links up to one level deep (max 10 links per
                  page).
                </p>
              </div>
            )}
            <div className='form-row'>
              <div className='form-group'>
                <label htmlFor='apiKeyInput'>
                  {providerLabel} API Key{' '}
                  <span className='optional-mark'>(optional)</span>
                </label>
                <div className='api-key-row'>
                  <input
                    id='apiKeyInput'
                    type={showKey ? 'text' : 'password'}
                    autoComplete='off'
                    placeholder={
                      provider === 'anthropic'
                        ? 'sk-ant-api03-…'
                        : provider === 'openai'
                          ? 'sk-…'
                          : 'AIza…'
                    }
                    value={key}
                    disabled={validating}
                    aria-describedby='apiKeyHint'
                    onChange={(event) => {
                      setKey(event.target.value);
                      setKeyStatus('');
                    }}
                  />
                  <button
                    type='button'
                    className={`toggle-key-btn ${showKey ? 'showing' : ''}`}
                    aria-label={showKey ? 'Hide API key' : 'Show API key'}
                    aria-pressed={showKey}
                    onClick={() => setShowKey(!showKey)}
                  >
                    <svg
                      id='eyeOffIcon'
                      width='20'
                      height='20'
                      viewBox='0 0 24 24'
                      fill='none'
                      stroke='currentColor'
                      strokeWidth='1.5'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                      aria-hidden='true'
                    >
                      <path d='M17.94 17.94A10.07 10.07 0 0 1 12 20C5 20 1 12 1 12a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19' />
                      <line x1='1' y1='1' x2='23' y2='23' />
                    </svg>
                    <svg
                      id='eyeIcon'
                      width='20'
                      height='20'
                      viewBox='0 0 24 24'
                      fill='none'
                      stroke='currentColor'
                      strokeWidth='1.5'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                      aria-hidden='true'
                    >
                      <path d='M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z' />
                      <circle cx='12' cy='12' r='3' />
                    </svg>
                  </button>
                  <button
                    type='button'
                    className='validate-key-btn'
                    disabled={validating}
                    aria-label='Validate API key'
                    onClick={() => void validateKey()}
                  >
                    {validating ? 'Checking…' : 'Validate'}
                  </button>
                </div>
                <p id='apiKeyHint' className='field-hint'>
                  Without a key, only programmatic checks run. Never stored or
                  logged.
                </p>
                <p
                  className={`key-validate-status ${validating ? 'validating' : keyStatus === 'Key is valid.' ? 'valid' : 'invalid'}`}
                  role='status'
                  hidden={!keyStatus}
                >
                  {keyStatus}
                </p>
              </div>
              <div className='form-group'>
                <label htmlFor='modelSelect'>Model</label>
                <select
                  id='modelSelect'
                  name='model'
                  value={model}
                  disabled={validating || !models.length}
                  onChange={(event) => {
                    setModel(event.target.value);
                    setKey('');
                    setKeyStatus('');
                  }}
                >
                  {(['anthropic', 'openai', 'gemini'] as const).map(
                    (group) =>
                      models.some((option) => option.provider === group) && (
                        <optgroup
                          key={group}
                          label={
                            group === 'anthropic'
                              ? 'Claude (Anthropic)'
                              : group === 'openai'
                                ? 'OpenAI'
                                : 'Gemini (Google)'
                          }
                        >
                          {models
                            .filter((option) => option.provider === group)
                            .map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.label}
                              </option>
                            ))}
                        </optgroup>
                      )
                  )}
                </select>
              </div>
            </div>
            <button
              type='submit'
              className='audit-btn'
              disabled={!models.length || validating}
            >
              {busy ? 'Running…' : 'Run Audit'}
            </button>
          </fieldset>
          {error && (
            <p
              ref={errorBox}
              tabIndex={-1}
              role='alert'
              className='audit-error'
            >
              {error}{' '}
              {!models.length && (
                <button
                  type='button'
                  className='browse-link'
                  onClick={() => void loadModels()}
                >
                  Reload model list
                </button>
              )}
            </p>
          )}
        </form>
        <div className='sr-only' role='status' aria-live='polite'>
          {busy
            ? progress?.message
            : result
              ? 'Audit complete. Results are available below.'
              : ''}
        </div>
        {(busy || result) && (
          <div className='audit-results'>
            {busy && (
              <div className='audit-progress'>
                <div className='progress-message'>{progress?.message}</div>
                <div
                  className='progress-bar-track'
                  role='progressbar'
                  aria-label='Current audit stage progress'
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={percent}
                >
                  <div
                    className='progress-bar-fill'
                    style={{ width: `${percent}%` }}
                  />
                </div>
                <div className='progress-detail'>{progressDetail}</div>
              </div>
            )}
            {result && (
              <div aria-labelledby='results-heading'>
                <h2
                  id='results-heading'
                  ref={resultHeading}
                  tabIndex={-1}
                  className='sr-only'
                >
                  Audit results
                </h2>
                <AuditResults result={result} />
              </div>
            )}
          </div>
        )}
        <div className='survey-container'>
          <a
            href='https://docs.google.com/forms/d/e/1FAIpQLSdWsgKpL2cK6Y2v9uYgQ3UbfmJQKNWrcCA_0YoMXzZMEnLuYA/viewform?usp=header'
            className='survey-btn'
            target='_blank'
            rel='noopener noreferrer'
          >
            Share Your Feedback
          </a>
        </div>
      </div>
    </section>
  );
}
