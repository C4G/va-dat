export const MODEL_CATALOG = [
  {
    id: 'claude-haiku-4-5-20251001',
    provider: 'anthropic',
    label: 'Claude Haiku 4.5 — faster, cheaper',
  },
  {
    id: 'claude-sonnet-5',
    provider: 'anthropic',
    label: 'Claude Sonnet 5 — higher quality',
  },
  {
    id: 'claude-opus-5',
    provider: 'anthropic',
    label: 'Claude Opus 5 — complex agentic/coding tasks',
  },
  {
    id: 'claude-fable-5',
    provider: 'anthropic',
    label: 'Claude Fable 5 — most capable, highest cost',
  },
  {
    id: 'gpt-4o-mini',
    provider: 'openai',
    label: 'GPT-4o mini — faster, cheaper',
  },
  { id: 'gpt-4o', provider: 'openai', label: 'GPT-4o — higher quality' },
  {
    id: 'gpt-4.1-mini',
    provider: 'openai',
    label: 'GPT-4.1 mini — faster, cheaper',
  },
  { id: 'gpt-4.1', provider: 'openai', label: 'GPT-4.1 — higher quality' },
  {
    id: 'gemini-flash-latest',
    provider: 'gemini',
    label: 'Gemini Flash — faster, cheaper',
  },
  {
    id: 'gemini-pro-latest',
    provider: 'gemini',
    label: 'Gemini Pro — higher quality',
  },
].map((model, order) => ({ ...model, order }));

export type ModelOption = (typeof MODEL_CATALOG)[number];
export type ModelSettings = {
  enabledModelIds: string[];
  defaultModelId: string;
};

export function validateModelSettings(value: unknown): ModelSettings {
  if (!value || typeof value !== 'object')
    throw new Error('Invalid model settings.');
  const { enabledModelIds, defaultModelId } = value as ModelSettings;
  if (
    !Array.isArray(enabledModelIds) ||
    enabledModelIds.length === 0 ||
    !enabledModelIds.every(
      (id) => typeof id === 'string' && MODEL_CATALOG.some((m) => m.id === id)
    ) ||
    new Set(enabledModelIds).size !== enabledModelIds.length ||
    typeof defaultModelId !== 'string' ||
    !enabledModelIds.includes(defaultModelId)
  ) {
    throw new Error(
      'Enable at least one supported model and select an enabled default.'
    );
  }
  return { enabledModelIds, defaultModelId };
}
