import type { Msg } from '../../state/settings.ts'

/** Результат дії біля місця, де її зроблено. Лише справжні збої — role="alert". */
export function Feedback({ msg }: { msg?: Msg }) {
  if (!msg) return null
  return (
    <p className={`feedback feedback-${msg.kind}`} role={msg.kind === 'error' ? 'alert' : 'status'}>
      {msg.text}
    </p>
  )
}
