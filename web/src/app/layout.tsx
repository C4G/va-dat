import { ImpersonationProvider } from '@/components/contexts/impersonation-context';
import { SiteShell } from '@/components/layout/site-shell';
import { ServiceWorkerRegistration } from '@/components/layout/service-worker-registration';
import { ThemeProvider } from '@/components/layout/theme-provider';
import { Toaster } from '@/components/ui/toaster';
import type { Metadata, Viewport } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import './legacy.css';
import './navbar.css';

const geistSans = localFont({
  src: './fonts/GeistVF.woff',
  variable: '--font-geist-sans',
  weight: '100 900',
});
const geistMono = localFont({
  src: './fonts/GeistMonoVF.woff',
  variable: '--font-geist-mono',
  weight: '100 900',
});

export const metadata: Metadata = {
  title: 'VA-DAT | Digital accessibility',
  description:
    'Accessibility auditing for Vision Aid, a Georgia Tech Computing for Good project.',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: 'VA-DAT',
  },
  formatDetection: {
    telephone: false,
  },
  icons: {
    icon: [
      { url: '/favicon-16x16.png', sizes: '16x16', type: 'image/png' },
      { url: '/favicon-32x32.png', sizes: '32x32', type: 'image/png' },
    ],
    apple: [
      { url: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
    ],
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#ffffff',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang='en'
      className='light'
      style={{ colorScheme: 'light' }}
      suppressHydrationWarning
    >
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider attribute='class'>
          <ImpersonationProvider>
            <ServiceWorkerRegistration />
            <SiteShell>{children}</SiteShell>
            <Toaster />
          </ImpersonationProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
