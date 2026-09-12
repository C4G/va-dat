import { describe, expect, it } from 'vitest';
import { MODEL_CATALOG, validateModelSettings } from './model-catalog';
const first = MODEL_CATALOG[0].id;
describe('model configuration', () => {
  it('accepts an enabled default', () =>
    expect(
      validateModelSettings({ enabledModelIds: [first], defaultModelId: first })
        .defaultModelId
    ).toBe(first));
  it.each([
    null,
    {},
    { enabledModelIds: [], defaultModelId: first },
    { enabledModelIds: ['unknown'], defaultModelId: 'unknown' },
    { enabledModelIds: [first], defaultModelId: 'gpt-4o' },
    { enabledModelIds: [first, first], defaultModelId: first },
  ])('rejects invalid settings %j', (value) =>
    expect(() => validateModelSettings(value)).toThrow()
  );
});
