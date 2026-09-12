import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useTheme } from 'next-themes';
import { useIsDarkTheme } from '@/hooks/use-is-dark-theme';
import { ThemeProvider } from './theme-provider';

function Probe() {
  const { forcedTheme } = useTheme();
  const dark = useIsDarkTheme();
  return (
    <p>
      {forcedTheme}:{dark ? 'dark grid' : 'light grid'}
    </p>
  );
}
afterEach(() => localStorage.removeItem('theme'));
describe('light-only template theme', () => {
  it.each(['dark', 'system'])(
    'overrides the saved %s theme for pages and grids',
    async (preference) => {
      localStorage.setItem('theme', preference);
      render(
        <ThemeProvider attribute='class' defaultTheme='dark' enableSystem>
          <Probe />
        </ThemeProvider>
      );
      expect(screen.getByText('light:light grid')).toBeInTheDocument();
      await waitFor(() =>
        expect(document.documentElement).toHaveClass('light')
      );
      expect(document.documentElement).not.toHaveClass('dark');
    }
  );
});
