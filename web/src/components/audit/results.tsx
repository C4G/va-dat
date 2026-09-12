'use client';
import { Fragment, useEffect, useId, useRef, useState } from 'react';
import type { AuditResult } from '@/lib/audit-stream';

function text(value: unknown) {
  return typeof value === 'string'
    ? value
    : (JSON.stringify(value, null, 2) ?? '');
}
function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function issueCount(parsed: unknown) {
  if (Array.isArray(parsed)) return parsed.length;
  const record = object(parsed);
  if (!record) return 0;
  for (const key of ['issues', 'findings', 'problems', 'violations']) {
    if (Array.isArray(record[key]) && record[key].length)
      return record[key].length;
  }
  return Object.entries(record).filter(
    ([key, value]) => key.startsWith('is_') && value === false
  ).length;
}
function Chevron({ className }: { className: string }) {
  return (
    <svg
      className={className}
      aria-hidden='true'
      viewBox='0 0 24 24'
      fill='none'
      stroke='currentColor'
      strokeWidth='2.5'
      strokeLinecap='round'
      strokeLinejoin='round'
    >
      <polyline points='6 9 12 15 18 9' />
    </svg>
  );
}
function IssueCard({ value }: { value: unknown }) {
  const item = object(value);
  if (!item)
    return (
      <div className='issue-card'>
        <p className='issue-desc'>{text(value)}</p>
      </div>
    );
  const description = [
    'issue',
    'problem',
    'description',
    'reason',
    'text',
    'finding',
  ].find((key) => item[key]);
  const element = ['element', 'selector', 'xpath', 'path', 'tag'].find(
    (key) => item[key]
  );
  const fix = [
    'recommended_fix',
    'recommendation',
    'suggestion',
    'fix',
    'remedy',
    'proposed_fix',
  ].find((key) => item[key]);
  const rest = Object.entries(item).filter(
    ([key]) => ![description, element, fix, 'impact'].includes(key)
  );
  return (
    <div className='issue-card'>
      {description && <p className='issue-desc'>{text(item[description])}</p>}
      {element && <code className='issue-element'>{text(item[element])}</code>}
      {fix && (
        <p className='issue-fix'>
          <strong>Fix:</strong> {text(item[fix])}
        </p>
      )}
      {!!item.impact && (
        <span
          className={`impact-badge impact-${text(item.impact).toLowerCase()}`}
        >
          {text(item.impact)}
        </span>
      )}
      {!!rest.length && (
        <dl className='issue-meta'>
          {rest.map(([key, value]) => (
            <Fragment key={key}>
              <dt>{key}</dt>
              <dd>{text(value)}</dd>
            </Fragment>
          ))}
        </dl>
      )}
    </div>
  );
}
function LLMBody({ parsed }: { parsed: unknown }) {
  if (!parsed) return <p className='llm-empty'>No response data.</p>;
  if (Array.isArray(parsed))
    return parsed.length ? (
      parsed.map((value, index) => <IssueCard key={index} value={value} />)
    ) : (
      <p className='llm-empty'>✓ No issues found.</p>
    );
  const record = object(parsed);
  if (!record || record.raw)
    return <pre className='llm-json'>{text(record?.raw ?? parsed)}</pre>;
  return (
    <div className='llm-object'>
      {Object.entries(record).map(([key, value]) => {
        const label = key.replaceAll('_', ' ');
        if (
          typeof value === 'boolean' ||
          (Array.isArray(value) && !value.length)
        ) {
          const ok = value !== false;
          return (
            <div className='llm-obj-row' key={key}>
              <span
                className={`check-icon ${ok ? 'check-ok' : 'check-fail'}`}
                aria-label={ok ? 'pass' : 'fail'}
              >
                {ok ? '✓' : '✗'}
              </span>
              <span className='llm-obj-key'>{label}</span>
              {Array.isArray(value) && (
                <span className='llm-obj-empty'>none</span>
              )}
            </div>
          );
        }
        if (Array.isArray(value))
          return (
            <div className='llm-obj-section' key={key}>
              <p className='llm-obj-section-label'>
                {label} ({value.length})
              </p>
              {value.map((item, index) => (
                <IssueCard key={index} value={item} />
              ))}
            </div>
          );
        return (
          <div className='llm-obj-row llm-obj-string' key={key}>
            <span className='llm-obj-key'>{label}</span>
            <span className='llm-obj-val'>{text(value)}</span>
          </div>
        );
      })}
    </div>
  );
}
function Prompt({
  name,
  result,
}: {
  name: string;
  result: Record<string, unknown>;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const count = issueCount(result.parsed);
  const status =
    result.status === 'dry_run'
      ? ['dry-run', 'dry run']
      : result.status === 'error'
        ? ['error', 'API error']
        : count > 0
          ? ['has-issues', `${count} issue${count === 1 ? '' : 's'}`]
          : result.parsed
            ? ['pass', 'pass']
            : null;
  return (
    <div className={`llm-prompt ${open ? 'open' : ''}`}>
      <button
        type='button'
        className='llm-prompt-header'
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <span className='llm-prompt-name'>{name.replaceAll('_', ' ')}</span>
        <span className='llm-prompt-tags'>
          {!!result.checklist && (
            <span className='llm-checklist-tag'>{text(result.checklist)}</span>
          )}
          {Array.isArray(result.wcag_criteria) &&
            result.wcag_criteria.slice(0, 5).map((criterion, index) => (
              <span className='wcag-tag' key={index}>
                {text(criterion)}
              </span>
            ))}
          {status && (
            <span className={`llm-badge ${status[0]}`}>{status[1]}</span>
          )}
        </span>
        <Chevron className='llm-chevron' />
      </button>
      <div id={id} className='llm-prompt-body' hidden={!open}>
        {result.status === 'error' ? (
          <p className='llm-error-message'>
            {text(result.error || 'The API call failed for an unknown reason.')}
          </p>
        ) : (
          <LLMBody parsed={result.parsed} />
        )}
      </div>
    </div>
  );
}
function PageResults({
  result,
  nested = false,
}: {
  result: AuditResult;
  nested?: boolean;
}) {
  const findings = result.programmatic_findings || [];
  const prompts = Object.entries(result.llm_results || {});
  const Heading = nested ? 'h4' : 'h3';
  return (
    <>
      <div className='findings-section'>
        <Heading>
          Programmatic Findings{' '}
          <span className='findings-count'>{findings.length}</span>
        </Heading>
        {!findings.length ? (
          <p className='findings-empty'>✓ No programmatic issues found.</p>
        ) : (
          <div className='findings-table-wrapper'>
            <table className='findings-table'>
              <thead>
                <tr>
                  {['Rule ID', 'Rule Name', 'Description'].map((label) => (
                    <th scope='col' key={label}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {findings.map((finding, index) => (
                  <tr key={index}>
                    <td>
                      <code className='rule-id'>{text(finding.rule_id)}</code>
                    </td>
                    <td>{text(finding.rule_name)}</td>
                    <td>{text(finding.description)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {!!prompts.length && (
        <div className='findings-section'>
          <Heading>
            LLM Analysis{' '}
            <span className='findings-count'>
              {prompts.length} prompt{prompts.length === 1 ? '' : 's'}
            </span>
          </Heading>
          <div className='llm-findings'>
            {prompts.map(([name, value]) => (
              <Prompt key={name} name={name} result={value} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}
function PageNode({
  url,
  result,
  ancestors = [],
}: {
  url: string;
  result: AuditResult;
  ancestors?: string[];
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (ancestors.includes(url)) return null;
  const page = result.page_results?.[url] || { success: true };
  const count =
    (page.programmatic_findings?.length || 0) +
    Object.keys(page.llm_results || {}).length;
  return (
    <div className={`page-node ${open ? 'open' : ''}`}>
      <button
        type='button'
        className='page-node-header'
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <Chevron className='page-node-chevron' />
        <span className='page-node-url' title={url}>
          {url.replace(/^https?:\/\//, '')}
        </span>
        <span className={`page-node-badge ${count ? 'has-issues' : 'pass'}`}>
          {count ? `${count} issue${count === 1 ? '' : 's'}` : 'pass'}
        </span>
      </button>
      <div id={id} className='page-node-body' hidden={!open}>
        <PageResults result={page} nested />
      </div>
      {!!result.crawl_tree?.[url]?.length && (
        <div className='page-node-children'>
          {result.crawl_tree[url].map((child) => (
            <PageNode
              key={child}
              url={child}
              result={result}
              ancestors={[...ancestors, url]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
export function AuditResults({ result }: { result: AuditResult }) {
  const download = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (!result.csv_report) return;
    const url = URL.createObjectURL(
      new Blob([result.csv_report], { type: 'text/csv;charset=utf-8' })
    );
    if (download.current) download.current.href = url;
    return () => URL.revokeObjectURL(url);
  }, [result]);
  const summary = result.summary || {};
  const llmCount = Object.keys(result.llm_results || {}).length;
  const total = (result.programmatic_findings?.length || 0) + llmCount;
  const stats: [unknown, string][] = [
    [
      summary.programmatic_count ?? result.programmatic_findings?.length ?? 0,
      'Programmatic Issues',
    ],
    [summary.llm_prompts_run ?? llmCount, 'LLM Prompts Run'],
  ];
  if (Number(summary.llm_prompts_skipped) > 0)
    stats.push([summary.llm_prompts_skipped, 'Prompts Skipped']);
  if (Number(summary.pages) > 1) stats.push([summary.pages, 'Pages Audited']);
  if (typeof summary.estimated_cost_usd === 'number')
    stats.push([`$${summary.estimated_cost_usd.toFixed(4)}`, 'Est. Cost']);
  const pages = Object.keys(result.page_results || {});
  const children = new Set(Object.values(result.crawl_tree || {}).flat());
  const roots = pages.filter((url) => !children.has(url));
  return (
    <>
      <div className='audit-summary'>
        {stats.map(([value, label]) => (
          <div className='summary-stat' key={label}>
            <span className='stat-num'>{text(value)}</span>
            <span className='stat-label'>{label}</span>
          </div>
        ))}
      </div>
      {!!summary.dry_run && (
        <p className='audit-notice'>
          No API key provided — LLM analysis was skipped. Only programmatic
          findings are shown.
        </p>
      )}
      {pages.length ? (
        <div className='page-tree' aria-label='Audited pages'>
          {(roots.length ? roots : pages.slice(0, 1)).map((url) => (
            <PageNode key={url} url={url} result={result} />
          ))}
        </div>
      ) : (
        <PageResults result={result} />
      )}
      {result.csv_report && (
        <div className='download-section'>
          <p className='download-desc'>
            Full report ready — {total} findings across programmatic checks and{' '}
            {llmCount} LLM prompts.
          </p>
          <a
            ref={download}
            className='download-btn'
            download='visionaid-report.csv'
          >
            <svg
              aria-hidden='true'
              viewBox='0 0 24 24'
              fill='none'
              stroke='currentColor'
              strokeWidth='2'
              strokeLinecap='round'
              strokeLinejoin='round'
            >
              <path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' />
              <polyline points='7 10 12 15 17 10' />
              <line x1='12' y1='15' x2='12' y2='3' />
            </svg>
            Download Report (CSV)
          </a>
        </div>
      )}
    </>
  );
}
