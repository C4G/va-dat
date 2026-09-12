import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuditResults } from './results';

describe('original results presentation', () => {
  it('renders summary cards, original table columns and keyboard-expandable safe issue cards', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <AuditResults
        result={{
          success: true,
          summary: {
            programmatic_count: 1,
            llm_prompts_run: 1,
            estimated_cost_usd: 0.0123,
          },
          programmatic_findings: [
            {
              rule_id: 'IMG',
              rule_name: 'Image alternative',
              description: 'Missing alt',
            },
          ],
          llm_results: {
            image_check: {
              status: 'success',
              checklist: 'Images',
              wcag_criteria: ['1.1.1'],
              parsed: {
                issues: [
                  {
                    description: '<img src=x onerror=alert(1)>',
                    element: '<img>',
                    recommended_fix: 'Add descriptive alt text',
                    impact: 'serious',
                    source: 'example',
                  },
                ],
                is_accessible: false,
              },
            },
          },
        }}
      />
    );
    expect(screen.getByText('$0.0123')).toHaveClass('stat-num');
    expect(
      screen.getAllByRole('columnheader').map((cell) => cell.textContent)
    ).toEqual(['Rule ID', 'Rule Name', 'Description']);
    const prompt = screen.getByRole('button', { name: /image check/ });
    expect(prompt).toHaveAttribute('aria-expanded', 'false');
    prompt.focus();
    await user.keyboard('{Enter}');
    expect(prompt).toHaveAttribute('aria-expanded', 'true');
    expect(prompt.parentElement).toHaveClass('open');
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();
    expect(screen.getByText('Add descriptive alt text')).toBeVisible();
    expect(screen.getByText('serious')).toHaveClass('impact-serious');
    expect(container.querySelector('img')).toBeNull();
    await user.keyboard(' ');
    expect(prompt).toHaveAttribute('aria-expanded', 'false');
  });
  it('expands nested page findings without recursing forever on cycles', async () => {
    const user = userEvent.setup();
    render(
      <AuditResults
        result={{
          success: true,
          page_results: {
            'https://example.org': { success: true },
            'https://example.org/a': { success: true },
          },
          crawl_tree: {
            'https://example.org': ['https://example.org/a'],
            'https://example.org/a': ['https://example.org'],
          },
        }}
      />
    );
    const pages = screen.getAllByRole('button');
    expect(pages).toHaveLength(2);
    await user.click(pages[1]);
    expect(pages[1]).toHaveAttribute('aria-expanded', 'true');
    expect(
      screen.getAllByText('✓ No programmatic issues found.')[1]
    ).toBeVisible();
  });
  it('offers the original CSV download and releases the object URL', () => {
    const create = vi.fn(() => 'blob:test-report');
    const revoke = vi.fn();
    vi.stubGlobal(
      'URL',
      Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
    );
    const { unmount } = render(
      <AuditResults
        result={{
          success: true,
          csv_report: 'rule,description\nIMG,Missing alt',
        }}
      />
    );
    expect(
      screen.getByRole('link', { name: 'Download Report (CSV)' })
    ).toHaveAttribute('href', 'blob:test-report');
    expect(create).toHaveBeenCalledWith(expect.any(Blob));
    unmount();
    expect(revoke).toHaveBeenCalledWith('blob:test-report');
  });
});
