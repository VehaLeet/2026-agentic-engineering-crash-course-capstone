import type { NotificationsSettings } from '../../api/types.ts'
import { useSettings } from '../../state/settings.ts'
import { Feedback } from './Feedback.tsx'

export function NotificationsToggle({ notifications }: { notifications: NotificationsSettings }) {
  const setNotifications = useSettings((s) => s.setNotifications)
  const saving = useSettings((s) => s.pending.notifications ?? false)
  const feedback = useSettings((s) => s.feedback.notifications)
  return (
    <div>
      <label className="checkbox">
        <input
          type="checkbox" checked={notifications.enabled} disabled={saving}
          onChange={(e) => void setNotifications(e.target.checked)}
        />
        Надсилати сповіщення в Telegram
      </label>
      {!notifications.token_configured && (
        <p className="feedback feedback-warning" role="status">
          Токен бота не задано: сповіщення не надсилатимуться, доки на сервері не задано TELEGRAM_BOT_TOKEN.
        </p>
      )}
      <Feedback msg={feedback} />
    </div>
  )
}
