import { useCollect } from '../state/collect.ts'
import { useConnection } from '../state/connection.ts'
import { CollectButton } from './CollectButton.tsx'
import { ConnectionPanel } from './ConnectionPanel.tsx'
import { RecentErrors } from './RecentErrors.tsx'

export function StatusPanel() {
  const connection = useConnection((s) => s.connection)
  const running = useCollect((s) => s.collect.phase === 'running')
  // Поки наш запуск триває, /status показує його зі status: null — це не «перервано».
  const interrupted = !running && connection.state === 'ok' && connection.lastRunStatus === null && connection.lastCheck !== null
  return (
    <section className="card status">
      <ConnectionPanel connection={connection} />
      {interrupted && <p className="muted">Останній запуск не завершено</p>}
      {connection.state === 'ok' && (
        <>
          <CollectButton />
          <RecentErrors errors={connection.recentErrors} />
        </>
      )}
    </section>
  )
}
