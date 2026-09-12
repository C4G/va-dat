'use client';
import Link from 'next/link';
import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { useIsMounted } from '@/hooks/use-is-mounted';
import { useSession } from '@/lib/auth-client';
import { UserMenu } from './user-menu';

export function Header() {
  const { data } = useSession();
  const isMounted = useIsMounted();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const signedIn = isMounted && !!data?.user;
  const links = [
    { href: '/#about', label: 'About' },
    { href: '/#team', label: 'Team' },
    { href: '/#deliverables', label: 'Deliverables' },
    { href: '/#lighthouse', label: 'Lighthouse' },
    ...(signedIn && data?.user.role === 'ADMIN'
      ? [
          { href: '/admin/models', label: 'Models' },
          { href: '/users', label: 'Users' },
        ]
      : []),
  ];
  return (
    <header className='p5-navbar'>
      <nav className='p5-navbar-inner' aria-label='Primary navigation'>
        <Link
          href='/'
          className='p5-navbar-brand'
          onClick={() => setOpen(false)}
        >
          P5: Digital Accessibility
        </Link>
        <button
          type='button'
          className='p5-hamburger'
          aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={open}
          aria-controls='site-navigation'
          onClick={() => setOpen(!open)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setOpen(false);
          }}
        >
          <span />
          <span />
          <span />
        </button>
        <ul
          id='site-navigation'
          className={`p5-nav-links ${open ? 'is-open' : ''}`}
          onKeyDown={(event) => {
            // Portalled account menus/dialogs bubble React events through this
            // list, but Escape should close only that overlay, not navigation.
            if (!event.currentTarget.contains(event.target as Node)) return;
            if (event.key === 'Escape') {
              setOpen(false);
              document
                .querySelector<HTMLButtonElement>('.p5-hamburger')
                ?.focus();
            }
          }}
        >
          {links.map(({ href, label }) => (
            <li key={href}>
              <Link
                href={href}
                aria-current={href === pathname ? 'page' : undefined}
                className='p5-nav-link'
                onClick={() => setOpen(false)}
              >
                {label}
              </Link>
            </li>
          ))}
          <li>
            <Link
              href='/audit'
              className={`p5-nav-button ${pathname === '/audit' ? 'is-active' : ''}`}
              aria-current={pathname === '/audit' ? 'page' : undefined}
              onClick={() => setOpen(false)}
            >
              Audit Tool
            </Link>
          </li>
          <li className='p5-auth-actions'>
            {signedIn ? (
              <UserMenu triggerClassName='p5-account-trigger' />
            ) : (
              <>
                <Link
                  href='/signin'
                  className='p5-auth-button p5-auth-signin'
                  onClick={() => setOpen(false)}
                >
                  Sign In
                </Link>
                <Link
                  href='/signup'
                  className='p5-auth-button p5-auth-signup'
                  onClick={() => setOpen(false)}
                >
                  Sign Up
                </Link>
              </>
            )}
          </li>
        </ul>
      </nav>
    </header>
  );
}
