import { MODEL_CATALOG } from '@/lib/model-catalog';
import { readModelSettings } from '@/lib/model-settings';

export const dynamic = 'force-dynamic';
export async function GET() {
  try {
    const settings = await readModelSettings();
    return Response.json(
      {
        models: MODEL_CATALOG.filter((m) =>
          settings.enabledModelIds.includes(m.id)
        ),
        defaultModelId: settings.defaultModelId,
      },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch {
    return Response.json(
      { error: 'Model configuration is unavailable. Try again later.' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
