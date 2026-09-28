import type { Run } from '../api/types.ts'
import { useCollect, type Collect } from '../state/collect.ts'

function fullDate(date: string): string {
  const [y, m, d] = date.split('-')
  return `${d}.${m}.${y}`
}

function resultMessage(run: Run): { text: string; alert: boolean } {
  switch (run.status) {
    case 'success':
      return { text: `Дані оновлено: ${run.changed_days.map(fullDate).join(', ')}`, alert: false }
    case 'no_changes':
      return { text: 'Нових даних немає', alert: false }
    case 'no_data':
      return { text: 'ОРЕЕ ще не опублікував дані', alert: false }
    case 'skipped_locked':
      return { text: 'Збір уже виконується, спробуйте за хвилину', alert: false }
    case 'error':
      return { text: `Помилка збору: ${run.error_message ?? 'невідома помилка'}`, alert: true }
    case null:
      return { text: 'Збір виконується…', alert: false }
  }
}

function Message({ collect }: { collect: Collect }) {
  switch (collect.phase) {
    case 'idle':
    case 'running':
      return null
    case 'timeout':
      return <p role="status">Збір триває довше, ніж очікувалось</p>
    case 'failed':
      return <p role="alert">{collect.message}</p>
    case 'done': {
      const { text, alert } = resultMessage(collect.run)
      return <p role={alert ? 'alert' : 'status'}>{text}</p>
    }
  }
}

export function CollectButton() {
  const collect = useCollect((s) => s.collect)
  const start = useCollect((s) => s.start)
  const running = collect.phase === 'running'
  return (
    <div className="collect">
      <button type="button" onClick={() => void start()} disabled={running} aria-busy={running}>
        {running ? 'Збір виконується…' : 'Оновити зараз'}
      </button>
      <Message collect={collect} />
    </div>
  )
}

