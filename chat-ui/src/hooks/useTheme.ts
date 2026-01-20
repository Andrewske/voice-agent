import { useEffect, useState } from 'react'

type Theme = 'light' | 'dark'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('dark')

  useEffect(() => {
    // Check system preference
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const updateTheme = (isDark: boolean) => {
      const newTheme = isDark ? 'dark' : 'light'
      setTheme(newTheme)
      document.documentElement.classList.toggle('dark', isDark)
    }

    // Set initial theme
    updateTheme(mediaQuery.matches)

    // Listen for changes
    const handler = (e: MediaQueryListEvent) => updateTheme(e.matches)
    mediaQuery.addEventListener('change', handler)

    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  return { theme }
}
