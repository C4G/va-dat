import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SiteShell } from './site-shell';
import Home from '@/app/page';

const route = vi.hoisted(() => ({ pathname: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => route.pathname }));
vi.mock('./header', () => ({
  Header: () => <header>Shared navigation</header>,
}));
vi.mock('./footer', () => ({ Footer: () => <footer>Template footer</footer> }));

describe('shared site shell', () => {
  it.each(['/', '/audit', '/signup', '/signin', '/admin/models'])(
    'uses one shared header on %s',
    (pathname) => {
      route.pathname = pathname;
      render(
        <SiteShell>
          <p>Route content</p>
        </SiteShell>
      );
      expect(screen.getAllByRole('banner')).toHaveLength(1);
      expect(screen.getByRole('banner')).toHaveTextContent('Shared navigation');
      expect(screen.getByRole('main')).toHaveTextContent('Route content');
      expect(screen.queryByText('About the Project')).not.toBeInTheDocument();
    }
  );
  it('renders project sections on home without mounting a hidden audit', () => {
    const { container } = render(<Home />);
    expect(
      screen.getByRole('heading', { name: 'About the Project' })
    ).toBeVisible();
    expect(
      screen.queryByRole('heading', { name: 'Accessibility Audit Tool' })
    ).not.toBeInTheDocument();
    expect(container.querySelector('[hidden]')).toBeNull();
  });
});
