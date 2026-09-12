'use client';
import { usePathname } from 'next/navigation';
import { Header } from './header';

export function SiteShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const publicPage = pathname === '/' || pathname === '/audit';
  return (
    <>
      <a
        href='#main-content'
        className='focus:bg-background sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:p-3'
      >
        Skip to content
      </a>
      <Header />
      <main
        id='main-content'
        tabIndex={-1}
        className={
          publicPage
            ? 'legacy-site public-content'
            : 'min-h-[calc(100dvh-8.4rem)]'
        }
      >
        {children}
      </main>

      <div className='legacy-site public-footer'>
        <footer className='site-footer'>
          <div className='footer-inner container'>
            <p>Georgia Tech CS 6150 — Computing for Good</p>
            <p>
              Partner:{' '}
              <a href='https://dat.visionaid.org/'>
                Vision Aid Digital Accessibility Testing Team
              </a>
            </p>
            <p>© 2026</p>
          </div>
        </footer>
      </div>
    </>
  );
}
