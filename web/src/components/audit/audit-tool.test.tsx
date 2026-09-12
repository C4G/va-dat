import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuditTool } from './audit-tool';
const models = [
  { id: 'gpt-4o', provider: 'openai', label: 'GPT-4o', order: 0 },
];
const result = {
  success: true,
  summary: { dry_run: true },
  programmatic_findings: [
    {
      rule_id: 'IMG',
      rule_name: 'Missing alt',
      description: '<script>alert(1)</script>',
    },
  ],
  llm_results: {
    images: { status: 'success', parsed: { issue: 'Missing alt' } },
  },
};
beforeEach(() => {
  vi.mocked(fetch).mockImplementation(async (input) => {
    if (input === '/api/models')
      return Response.json({ models, defaultModelId: 'gpt-4o' });
    if (input === '/api/validate-key') return Response.json({ valid: true });
    return Response.json(result);
  });
});
describe('public audit interface', () => {
  it('runs anonymous HTML audits and renders untrusted output as text', async () => {
    const user = userEvent.setup();
    const { container } = render(<AuditTool />);
    await screen.findByRole('option', { name: 'GPT-4o' });
    await user.click(screen.getByText('Or paste HTML directly'));
    await user.type(
      screen.getByLabelText('Paste HTML source code'),
      '<img src="x">'
    );
    await user.click(screen.getByRole('button', { name: 'Run Audit' }));
    await screen.findByRole('heading', { name: 'Audit results' });
    expect(screen.getAllByText('<script>alert(1)</script>')).toHaveLength(1);
    expect(container.querySelector('script')).toBeNull();
    expect(
      screen.getByRole('heading', { name: 'Audit results' })
    ).toHaveFocus();
    expect(fetch).toHaveBeenCalledWith(
      '/api/audit',
      expect.objectContaining({
        body: JSON.stringify({
          model: 'gpt-4o',
          openai_api_key: '',
          html_content: '<img src="x">',
        }),
      })
    );
  });
  it.each([
    ['URL — Single Page', '/api/audit/url'],
    ['URL — With Crawl', '/api/audit/url/nested'],
  ])('preserves %s', async (label, path) => {
    const user = userEvent.setup();
    render(<AuditTool />);
    await screen.findByRole('option', { name: 'GPT-4o' });
    await user.click(screen.getByLabelText(label));
    await user.type(
      screen.getByLabelText(/URL.*required/),
      'https://example.org'
    );
    await user.click(screen.getByRole('button', { name: 'Run Audit' }));
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(path, expect.anything())
    );
  });
  it('loads uploaded HTML and validates the selected provider key', async () => {
    const user = userEvent.setup();
    render(<AuditTool />);
    await screen.findByRole('option', { name: 'GPT-4o' });
    const file = new File(['<p>Uploaded</p>'], 'page.html', {
      type: 'text/html',
    });
    Object.defineProperty(file, 'text', {
      value: async () => '<p>Uploaded</p>',
    });
    fireEvent.change(screen.getByLabelText(/HTML File.*required/), {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(screen.getByLabelText('Paste HTML source code')).toHaveValue(
        '<p>Uploaded</p>'
      )
    );
    await user.type(
      screen.getByLabelText('OpenAI API Key (optional)'),
      'test-key'
    );
    await user.click(screen.getByRole('button', { name: 'Validate API key' }));
    await screen.findByText('Key is valid.');
    expect(fetch).toHaveBeenCalledWith(
      '/api/validate-key',
      expect.objectContaining({
        body: JSON.stringify({ provider: 'openai', api_key: 'test-key' }),
      })
    );
  });
  it('clears credentials when changing provider', async () => {
    vi.mocked(fetch).mockResolvedValue(
      Response.json({
        models: [
          ...models,
          {
            id: 'gemini-pro-latest',
            provider: 'gemini',
            label: 'Gemini Pro',
            order: 1,
          },
        ],
        defaultModelId: 'gpt-4o',
      })
    );
    const user = userEvent.setup();
    render(<AuditTool />);
    await screen.findByRole('option', { name: 'GPT-4o' });
    await user.type(
      screen.getByLabelText('OpenAI API Key (optional)'),
      'test-key'
    );
    await user.selectOptions(
      screen.getByLabelText('Model'),
      'gemini-pro-latest'
    );
    expect(screen.getByLabelText('Gemini API Key (optional)')).toHaveValue('');
  });
  it('retries model configuration errors without changing the initial layout', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      Response.json({ error: 'Unavailable' }, { status: 503 })
    );
    const user = userEvent.setup();
    render(<AuditTool />);
    await user.click(
      await screen.findByRole('button', { name: 'Reload model list' })
    );
    await screen.findByRole('option', { name: 'GPT-4o' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('shows an error and allows retry when Python fails', async () => {
    vi.mocked(fetch).mockImplementation(async (input) =>
      input === '/api/models'
        ? Response.json({ models, defaultModelId: 'gpt-4o' })
        : Response.json({ error: 'Audit service unavailable' }, { status: 502 })
    );
    const user = userEvent.setup();
    render(<AuditTool />);
    await screen.findByRole('option', { name: 'GPT-4o' });
    await user.click(screen.getByText('Or paste HTML directly'));
    await user.type(
      screen.getByLabelText('Paste HTML source code'),
      '<p>Test</p>'
    );
    await user.click(screen.getByRole('button', { name: 'Run Audit' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Audit service unavailable'
    );
    expect(screen.getByRole('button', { name: 'Run Audit' })).toBeEnabled();
  });
});
