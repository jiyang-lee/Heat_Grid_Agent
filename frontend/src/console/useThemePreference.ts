import { useEffect, useState } from 'react'

export type ThemePreference = 'system' | 'light' | 'dark'
export type ResolvedTheme = Exclude<ThemePreference, 'system'>

const STORAGE_KEY = 'heatgrid:theme-preference'

function savedPreference(): ThemePreference {
  const value = window.localStorage.getItem(STORAGE_KEY)
  return value === 'light' || value === 'dark' || value === 'system' ? value : 'system'
}

function systemTheme(): ResolvedTheme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useThemePreference() {
  const [preference, setPreference] = useState<ThemePreference>(savedPreference)
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => preference === 'system' ? systemTheme() : preference)

  useEffect(() => {
    const next = preference === 'system' ? systemTheme() : preference
    setResolvedTheme(next)
    document.documentElement.dataset.theme = next
    window.localStorage.setItem(STORAGE_KEY, preference)
    if (preference !== 'system') return undefined
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      const resolved = systemTheme()
      setResolvedTheme(resolved)
      document.documentElement.dataset.theme = resolved
    }
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [preference])

  return { preference, resolvedTheme, setPreference }
}
