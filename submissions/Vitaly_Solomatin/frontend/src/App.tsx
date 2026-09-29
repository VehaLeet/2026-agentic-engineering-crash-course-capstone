import { useEffect } from 'react'
import { DataView } from './components/DataView.tsx'
import { SettingsView } from './components/settings/SettingsView.tsx'
import { StatusPanel } from './components/StatusPanel.tsx'
import { Tabs } from './components/Tabs.tsx'
import { useTab } from './lib/tab.ts'
import { useConnection } from './state/connection.ts'

export default function App() {
  const check = useConnection((s) => s.check)
  const [tab, selectTab] = useTab()

  useEffect(() => {
    void check()
  }, [check])

  return (
    <>
      <header className="app-header">
        <h1>OREE DAM Monitor</h1>
        <Tabs tab={tab} onSelect={selectTab} />
      </header>
      <main>
        {tab === 'data' ? (
          <>
            <StatusPanel />
            <DataView />
          </>
        ) : (
          <SettingsView />
        )}
      </main>
    </>
  )
}
