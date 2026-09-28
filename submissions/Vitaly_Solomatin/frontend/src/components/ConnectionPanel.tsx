import type { Connection } from '../state/connection.ts'
import { formatKyiv } from '../lib/time.ts'

function when(iso: string | null): string {
  return iso ? formatKyiv(iso) : 'ще не було'
}

export function ConnectionPanel({ connection }: { connection: Connection }) {
  switch (connection.state) {
    case 'loading':
      return <section aria-busy="true">Перевіряю з'єднання з API…</section>
    case 'ok':
      return (
        <section>
          <p>З'єднання з API в порядку</p>
          <dl>
            <dt>Остання перевірка</dt>
            <dd>{when(connection.lastCheck)}</dd>
            <dt>Останнє оновлення даних</dt>
            <dd>{when(connection.lastUpdate)}</dd>
          </dl>
        </section>
      )
    case 'unauthorized':
      return (
        <section role="alert">
          <p>Потрібна автентифікація</p>
          {/* Перехід верхнього рівня гарантовано викликає системне вікно логіна браузера. */}
          <a href="/api/status">Увійти</a>
        </section>
      )
    case 'unavailable':
      return (
        <section role="alert">
          <p>Backend недоступний</p>
        </section>
      )
    case 'error':
      return (
        <section role="alert">
          <p>Помилка з'єднання з API: {connection.message}</p>
        </section>
      )
  }
}
