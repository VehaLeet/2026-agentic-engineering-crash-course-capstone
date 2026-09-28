import { useEffect } from 'react'
import { ConnectionPanel } from './components/ConnectionPanel.tsx'
import { DataView } from './components/DataView.tsx'
import { useConnection } from './state/connection.ts'

export default function App() {
  const connection = useConnection((s) => s.connection)
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
        <section className="card">
          <ConnectionPanel connection={connection} />
        </section>
        <DataView />
      </main>
    </>
  )
}
