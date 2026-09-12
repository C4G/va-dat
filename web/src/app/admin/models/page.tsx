import { getSession } from '@/lib/auth';
import { readModelSettings } from '@/lib/model-settings';
import { ModelSettingsForm } from '@/components/model-settings-form';
import { redirect } from 'next/navigation';
export const dynamic = 'force-dynamic';
export default async function ModelsPage() {
  const session = await getSession();
  if (!session) redirect('/signin');
  if (session.user.role !== 'ADMIN')
    return (
      <div className='mx-auto max-w-3xl p-8'>
        <h1>Administrator access required</h1>
      </div>
    );
  let settings;
  try {
    settings = await readModelSettings();
  } catch {
    return (
      <div className='p-8'>
        <h1>Model configuration is unavailable</h1>
        <p>Please try again later.</p>
      </div>
    );
  }
  return (
    <div className='mx-auto max-w-3xl space-y-6 p-8'>
      <h1 className='text-3xl font-bold'>Audit model settings</h1>
      <p>
        Choose which supported models appear in the public audit tool. Users
        supply their own API keys.
      </p>
      <ModelSettingsForm initial={settings} />
    </div>
  );
}
