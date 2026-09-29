import { useEffect, useState } from 'react'

export type Tab = 'data' | 'settings'

const SETTINGS_HASH = '#settings'

export function tabFromHash(hash: string): Tab {
  return hash === SETTINGS_HASH ? 'settings' : 'data'
}

/** Вкладка живе в location.hash: перезавантаження і «назад»/«вперед» працюють без маршрутизатора. */
export function useTab(): [Tab, (tab: Tab) => void] {
  const [tab, setTab] = useState<Tab>(() => tabFromHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setTab(tabFromHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const select = (next: Tab) => {
    window.location.hash = next === 'settings' ? SETTINGS_HASH : ''
    setTab(next)
  }
  return [tab, select]
}
