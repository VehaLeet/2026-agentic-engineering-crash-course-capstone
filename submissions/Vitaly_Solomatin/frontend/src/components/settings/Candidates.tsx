import { formatKyiv } from '../../lib/time.ts'
import { useSettings } from '../../state/settings.ts'

const TYPES: Record<string, string> = {
  private: 'особистий чат', group: 'група', supergroup: 'група', channel: 'канал',
}

/** Вибір отримувача з чатів, що нещодавно писали боту, замість ручного введення chat_id. */
export function Candidates({ tokenConfigured }: { tokenConfigured: boolean }) {
  const candidates = useSettings((s) => s.candidates)
  const find = useSettings((s) => s.findCandidates)
  const add = useSettings((s) => s.addCandidate)
  const adding = useSettings((s) => s.pending.adding ?? false)
  const searching = candidates.state === 'loading'

  return (
    <div className="candidates">
      <button type="button" disabled={!tokenConfigured || searching} onClick={() => void find()}>
        {searching ? 'Шукаємо…' : 'Знайти чати'}
      </button>
      {!tokenConfigured && <p className="muted">Пошук чатів недоступний: токен бота не задано.</p>}
      {candidates.state === 'error' && <p role="alert">{candidates.message}</p>}
      {candidates.state === 'ok' && candidates.items.length === 0 && (
        <p className="muted">
          Чатів не знайдено. Видно лише чати, що писали боту або додали його за останні 24 години.
        </p>
      )}
      {candidates.state === 'ok' && candidates.items.length > 0 && (
        <ul>
          {candidates.items.map((c) => (
            <li key={c.chat_id} className="candidate">
              <span>
                <strong>{c.title || c.chat_id}</strong>
                {c.username && <> <span className="muted">@{c.username}</span></>}
              </span>
              <span className="muted">{TYPES[c.type] ?? c.type}</span>
              <span className="muted">{formatKyiv(c.last_seen_at)}</span>
              {c.added ? (
                <span className="muted">вже додано</span>
              ) : (
                <button type="button" disabled={adding} onClick={() => void add(c.chat_id)}>Додати</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
