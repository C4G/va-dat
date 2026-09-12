import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Header } from './header';

const state = vi.hoisted(() => ({
  role: null as string | null,
  pathname: '/audit',
}));
vi.mock('next/navigation', () => ({ usePathname: () => state.pathname }));
vi.mock('@/hooks/use-is-mounted', () => ({ useIsMounted: () => true }));
vi.mock('@/lib/auth-client', () => ({
  useSession: () => ({
    data: state.role ? { user: { role: state.role } } : null,
  }),
}));
vi.mock('./user-menu', () => ({
  UserMenu: () => <button>Account menu</button>,
}));
beforeEach(() => {
  state.role = null;
  state.pathname = '/audit';
});

describe('shared original-style navbar', () => {
  it('keeps the P5 brand and original link order with auth links', () => {
    render(<Header />);
    expect(screen.getByRole('link', { name: 'Team' })).toHaveAttribute(
      'href',
      '/#team'
    );
    expect(screen.getByRole('link', { name: 'Lighthouse' })).toHaveAttribute(
      'href',
      '/#lighthouse'
    );
    expect(
      screen.getByRole('link', { name: 'P5: Digital Accessibility' })
    ).toHaveAttribute('href', '/');
    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual(
      [
        'P5: Digital Accessibility',
        'About',
        'Team',
        'Deliverables',
        'Lighthouse',
        'Audit Tool',
        'Sign In',
        'Sign Up',
      ]
    );
    expect(screen.getByRole('link', { name: 'Audit Tool' })).toHaveAttribute(
      'href',
      '/audit'
    );
    expect(screen.getByRole('link', { name: 'Audit Tool' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    expect(screen.getByRole('link', { name: 'Sign In' })).toHaveAttribute(
      'href',
      '/signin'
    );
    expect(screen.getByRole('link', { name: 'Sign Up' })).toHaveAttribute(
      'href',
      '/signup'
    );
  });
  it('closes mobile navigation on selection and Escape', async () => {
    const user = userEvent.setup();
    render(<Header />);
    const toggle = screen.getByRole('button', { name: 'Open navigation menu' });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(screen.getByRole('link', { name: 'Audit Tool' }));
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);
    screen.getByRole('link', { name: 'About' }).focus();
    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveFocus();
  });
  it.each(['STAFF', 'ADMIN'])(
    'shows account controls for %s and limits admin links',
    (role) => {
      state.role = role;
      render(<Header />);
      expect(
        screen.getByRole('button', { name: 'Account menu' })
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('link', { name: 'Sign In' })
      ).not.toBeInTheDocument();
      expect(Boolean(screen.queryByRole('link', { name: 'Models' }))).toBe(
        role === 'ADMIN'
      );
      expect(Boolean(screen.queryByRole('link', { name: 'Users' }))).toBe(
        role === 'ADMIN'
      );
    }
  );
});
