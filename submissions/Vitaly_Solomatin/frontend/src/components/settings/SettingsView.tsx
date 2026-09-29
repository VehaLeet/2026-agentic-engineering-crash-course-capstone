import { useEffect } from 'react'
import { useSettings } from '../../state/settings.ts'
import { NotificationsToggle } from './NotificationsToggle.tsx'
import { RecipientsList } from './RecipientsList.tsx'
import { ScheduleForm } from './ScheduleForm.tsx'

export function SettingsView() {
  const settings = useSettings((s) => s.settings)
  const load = useSettings((s) => s.load)

  useEffect(() => {
    void load()
  }, [load])

  if (settings.state === 'loading') return <section className="card"><p className="muted">Завантаження налаштувань…</p></section>
  if (settings.state !== 'ok') {
    return (
      <section className="card">
        <p role="alert">{settings.state === 'unavailable' ? 'Backend недоступний' : settings.message}</p>
        <button type="button" onClick={() => void load()}>Повторити</button>
      </section>
    )
  }
  return (
    <>
      <ScheduleForm schedule={settings.schedule} />
      <section className="card">
        <h2>Сповіщення в Telegram</h2>
        <NotificationsToggle notifications={settings.notifications} />
        <RecipientsList recipients={settings.recipients} tokenConfigured={settings.notifications.token_configured} />
      </section>
    </>
  )
}
