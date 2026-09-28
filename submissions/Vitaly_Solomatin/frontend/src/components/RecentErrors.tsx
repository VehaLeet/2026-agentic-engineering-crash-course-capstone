import type { Run } from '../api/types.ts'
import { formatKyiv } from '../lib/time.ts'

export function RecentErrors({ errors }: { errors: Run[] }) {
  if (errors.length === 0) return <p className="muted">Помилок збору немає</p>
  return (
    <div>
      <h2 className="subheading">Останні помилки збору</h2>
      <ul className="errors">
        {errors.map((e) => (
          <li key={e.id}>
            <time dateTime={e.started_at}>{formatKyiv(e.started_at)}</time> — {e.error_message ?? 'без опису'}
          </li>
        ))}
      </ul>
    </div>
  )
}
