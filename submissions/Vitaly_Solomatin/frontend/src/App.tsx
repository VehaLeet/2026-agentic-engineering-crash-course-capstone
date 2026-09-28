import { useEffect } from 'react'
import { DataView } from './components/DataView.tsx'
import { StatusPanel } from './components/StatusPanel.tsx'
import { useConnection } from './state/connection.ts'

export default function App() {
  const check = useConnection((s) => s.check)

  useEffect(() => {
    void check()
  }, [check])

  return (
    <>
      <header className="app-header">
        <h1>OREE DAM Monitor</h1>
      </header>
      <main>
        <StatusPanel />
        <DataView />
      </main>
    </>
  )
}
