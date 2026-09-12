import { prisma } from '@/lib/prisma';
import { validateModelSettings } from '@/lib/model-catalog';

export async function readModelSettings() {
  const settings = await prisma.modelConfiguration.findUniqueOrThrow({
    where: { id: 1 },
  });
  return validateModelSettings(settings);
}

export async function saveModelSettings(value: unknown) {
  const data = validateModelSettings(value);
  await prisma.modelConfiguration.update({ where: { id: 1 }, data });
  return data;
}
