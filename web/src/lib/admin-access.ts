import { getSession } from '@/lib/auth';

export async function requireAdmin() {
  const session = await getSession();
  if (!session)
    return Response.json({ error: 'Sign in to continue.' }, { status: 401 });
  if (session.user.role !== 'ADMIN')
    return Response.json(
      { error: 'Administrator access required.' },
      { status: 403 }
    );
  return null;
}

export function isSameOrigin(request: Request) {
  const expected = new URL(process.env.BETTER_AUTH_URL || request.url).origin;
  return request.headers.get('origin') === expected;
}
