import { useEffect } from 'react'
import { ConnectionPanel } from './components/ConnectionPanel.tsx'
import { useConnection } from './state/connection.ts'

export default function App() {
  const connection = useConnection((s) => s.connection)
  const check = useConnection((s) => s.check)

  useEffect(() => {
    void check()
  }, [check])

  return (
    <main>
      <h1>OREE DAM Monitor</h1>
      <ConnectionPanel connection={connection} />
    </main>
  )
}
