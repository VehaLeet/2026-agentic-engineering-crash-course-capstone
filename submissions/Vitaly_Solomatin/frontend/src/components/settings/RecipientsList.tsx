import { useState, type FormEvent } from 'react'
import type { Recipient } from '../../api/types.ts'
import { useSettings } from '../../state/settings.ts'
import { Candidates } from './Candidates.tsx'
import { Feedback } from './Feedback.tsx'

export function RecipientsList({ recipients, tokenConfigured }: { recipients: Recipient[]; tokenConfigured: boolean }) {
  const { addRecipient, toggleRecipient, removeRecipient, testRecipient } = useSettings()
  const pending = useSettings((s) => s.pending)
  const feedback = useSettings((s) => s.feedback)
  const [chatId, setChatId] = useState('')

  const add = async (e: FormEvent) => {
    e.preventDefault()
    const value = chatId.trim()
    if (!value || pending.adding) return
    if (await addRecipient(value)) setChatId('')
  }

  const remove = (id: string) => {
    if (window.confirm(`Видалити отримувача ${id}?`)) void removeRecipient(id)
  }

  return (
    <div className="recipients">
      <h3>Отримувачі</h3>
      {recipients.length === 0 ? (
        <p className="muted">
          Отримувачів немає. Людина має спершу написати боту /start, а канал — додати бота адміністратором.
        </p>
      ) : (
        <ul>
          {recipients.map((r) => {
            const busy = pending.recipients[r.chat_id]
            return (
              <li key={r.chat_id} className="recipient">
                <label className="checkbox">
                  <input
                    type="checkbox" checked={r.enabled} disabled={busy !== undefined}
                    aria-label={`Надсилати отримувачу ${r.chat_id}`}
                    onChange={(e) => void toggleRecipient(r.chat_id, e.target.checked)}
                  />
                  <code>{r.chat_id}</code>
                </label>
                <button
                  type="button" disabled={!tokenConfigured || busy !== undefined}
                  title={tokenConfigured ? undefined : 'Токен бота не задано'}
                  onClick={() => void testRecipient(r.chat_id)}
                >
                  {busy === 'test' ? 'Надсилаємо…' : 'Надіслати тест'}
                </button>
                <button type="button" disabled={busy !== undefined} onClick={() => remove(r.chat_id)}>
                  Видалити
                </button>
                <Feedback msg={feedback.recipients[r.chat_id]} />
              </li>
            )
          })}
        </ul>
      )}
      {!tokenConfigured && recipients.length > 0 && (
        <p className="muted">Тестове повідомлення недоступне: токен бота не задано.</p>
      )}
      <form className="settings-form" onSubmit={(e) => void add(e)}>
        <label>
          chat_id
          <input value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="123456789 або @channel" />
        </label>
        <button type="submit" disabled={chatId.trim() === '' || pending.adding}>
          {pending.adding ? 'Додаємо…' : 'Додати'}
        </button>
      </form>
      <Feedback msg={feedback.adding} />
      <Candidates tokenConfigured={tokenConfigured} />
    </div>
  )
}
