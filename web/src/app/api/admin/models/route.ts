import { isSameOrigin, requireAdmin } from '@/lib/admin-access';
import { MODEL_CATALOG, validateModelSettings } from '@/lib/model-catalog';
import { readModelSettings, saveModelSettings } from '@/lib/model-settings';

export const dynamic = 'force-dynamic';
export async function GET() {
  const denied = await requireAdmin();
  if (denied) return denied;
  try {
    return Response.json(
      { models: MODEL_CATALOG, ...(await readModelSettings()) },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch {
    return Response.json(
      { error: 'Model configuration is unavailable.' },
      { status: 503 }
    );
  }
}

export async function PUT(request: Request) {
  const denied = await requireAdmin();
  if (denied) return denied;
  if (!isSameOrigin(request))
    return Response.json(
      { error: 'Same-origin request required.' },
      { status: 403 }
    );
  let settings;
  try {
    settings = validateModelSettings(await request.json());
  } catch {
    return Response.json(
      {
        error:
          'Enable at least one supported model and select an enabled default.',
      },
      { status: 400 }
    );
  }
  try {
    return Response.json(await saveModelSettings(settings), {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch {
    return Response.json(
      { error: 'Could not save model configuration.' },
      { status: 503 }
    );
  }
}
