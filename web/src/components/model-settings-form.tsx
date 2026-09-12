'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { MODEL_CATALOG, type ModelSettings } from '@/lib/model-catalog';

export function ModelSettingsForm({ initial }: { initial: ModelSettings }) {
  const [settings, setSettings] = useState(initial);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/models', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setSettings(data);
      setMessage('Model settings saved.');
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Could not save model settings.'
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className='space-y-6'>
      <fieldset disabled={busy} className='space-y-3'>
        <legend className='mb-3 font-semibold'>Available models</legend>
        {MODEL_CATALOG.map((model) => (
          <label className='flex items-start gap-3' key={model.id}>
            <input
              className='mt-1'
              type='checkbox'
              checked={settings.enabledModelIds.includes(model.id)}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  enabledModelIds: e.target.checked
                    ? [...settings.enabledModelIds, model.id]
                    : settings.enabledModelIds.filter((id) => id !== model.id),
                })
              }
            />
            <span>
              {model.label}
              <span className='text-muted-foreground block text-sm'>
                {model.provider} · {model.id}
              </span>
            </span>
          </label>
        ))}
        <label className='block pt-4'>
          Default model
          <select
            className='audit-input mt-2'
            value={settings.defaultModelId}
            onChange={(e) =>
              setSettings({ ...settings, defaultModelId: e.target.value })
            }
          >
            {!settings.enabledModelIds.includes(settings.defaultModelId) && (
              <option value={settings.defaultModelId} disabled>
                Select an enabled default
              </option>
            )}
            {MODEL_CATALOG.filter((m) =>
              settings.enabledModelIds.includes(m.id)
            ).map((m) => (
              <option value={m.id} key={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      </fieldset>
      <Button disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</Button>
      <p role='status'>{message}</p>
    </form>
  );
}
