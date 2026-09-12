import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'standalone',
  serverExternalPackages: ['web-push'],
  // The original project page is the single source for course/project content.
  async redirects() {
    return [
      { source: '/team', destination: '/#team', permanent: false },
      { source: '/team/lighthouse-report', destination: '/#lighthouse', permanent: false },
      { source: '/team/project-description', destination: '/#about', permanent: false },
      { source: '/team/project-goal', destination: '/#goal', permanent: false },
      { source: '/team/demo', destination: '/#hero', permanent: false },
      ...['presentation-slides', 'weekly-updates', 'peer-evaluations'].map(page => ({source: `/team/${page}`, destination: '/#deliverables', permanent: false})),
    ];
  },
  // Ensure service worker and manifest are accessible
  async headers() {
    return [
      {
        source: '/sw.js',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-cache, no-store, must-revalidate',
          },
          {
            key: 'Service-Worker-Allowed',
            value: '/',
          },
        ],
      },
      {
        source: '/manifest.webmanifest',
        headers: [
          {
            key: 'Content-Type',
            value: 'application/manifest+json',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
