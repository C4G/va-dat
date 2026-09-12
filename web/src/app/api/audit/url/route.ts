import { proxyAudit } from '@/lib/audit-proxy';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export function POST(request: Request) {
  return proxyAudit(request, '/api/audit/url');
}
