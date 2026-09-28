import { HOURLY_LIMIT_DAYS, type PresetId } from '../lib/kyiv.ts'
import { hourlyAllowed, usePrices } from '../state/prices.ts'

const PRESETS: [PresetId, string][] = [['7d', '7 днів'], ['30d', '30 днів'], ['year', 'Рік'], ['all', 'Уся історія']]

export function DataFilter() {
  const { range, resolution, setPreset, setRange, setResolution } = usePrices()
  const hourOk = hourlyAllowed(range)
  return (
    <section className="card filter" aria-label="Фільтр даних">
      <div role="group" aria-label="Період">
        {PRESETS.map(([id, label]) => <button key={id} type="button" onClick={() => setPreset(id)}>{label}</button>)}
      </div>
      <label>
        Від
        <input type="date" value={range.from} onChange={(e) => e.target.value && setRange({ ...range, from: e.target.value })} />
      </label>
      <label>
        До
        <input type="date" value={range.to} onChange={(e) => e.target.value && setRange({ ...range, to: e.target.value })} />
      </label>
      <div role="group" aria-label="Роздільність">
        <button type="button" aria-pressed={resolution === 'hour'} disabled={!hourOk} onClick={() => setResolution('hour')}>Погодинно</button>
        <button type="button" aria-pressed={resolution === 'day'} onClick={() => setResolution('day')}>Подобово</button>
      </div>
      {!hourOk && <p className="muted">Погодинно можна переглянути не більше {HOURLY_LIMIT_DAYS} діб</p>}
    </section>
  )
}
