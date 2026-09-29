import { useState, type FormEvent } from 'react'
import { INTERVAL_MAX, INTERVAL_MIN, type Schedule } from '../../api/types.ts'
import { intervalError } from '../../lib/interval.ts'
import { formatKyiv } from '../../lib/time.ts'
import { useSettings } from '../../state/settings.ts'
import { Feedback } from './Feedback.tsx'

export function ScheduleForm({ schedule }: { schedule: Schedule }) {
  const save = useSettings((s) => s.saveSchedule)
  const saving = useSettings((s) => s.pending.schedule ?? false)
  const feedback = useSettings((s) => s.feedback.schedule)
  // Чернетка локальна: після відмови сервера введене лишається у формі.
  const [enabled, setEnabled] = useState(schedule.enabled)
  const [interval, setIntervalValue] = useState(String(schedule.interval_minutes))

  const problem = intervalError(interval)
  const dirty = enabled !== schedule.enabled || interval !== String(schedule.interval_minutes)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (problem || !dirty || saving) return
    void save({ enabled, interval_minutes: Number(interval) })
  }

  return (
    <section className="card">
      <h2>Розклад збору</h2>
      <form className="settings-form" onSubmit={submit}>
        <label className="checkbox">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Збирати дані автоматично
        </label>
        <label>
          Інтервал, хвилин
          <input
            type="number" inputMode="numeric" min={INTERVAL_MIN} max={INTERVAL_MAX} step={1}
            value={interval} onChange={(e) => setIntervalValue(e.target.value)}
            aria-invalid={problem !== null} aria-describedby="interval-error"
          />
        </label>
        {problem && <p id="interval-error" className="feedback feedback-error">{problem}</p>}
        <button type="submit" disabled={problem !== null || !dirty || saving}>
          {saving ? 'Збереження…' : 'Зберегти'}
        </button>
      </form>
      <p className="muted">
        Наступний запуск: {schedule.next_run_at ? formatKyiv(schedule.next_run_at) : 'не заплановано'}
      </p>
      <Feedback msg={feedback} />
    </section>
  )
}
