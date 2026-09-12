'use client';

import { useTheme } from 'next-themes';

export function useIsDarkTheme() {
  const { theme, systemTheme, forcedTheme } = useTheme();

  const isDarkTheme = forcedTheme
    ? forcedTheme === 'dark'
    : theme === 'dark' || (theme === 'system' && systemTheme === 'dark');

  return isDarkTheme;
}
