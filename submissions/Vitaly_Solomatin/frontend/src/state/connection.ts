import { create } from 'zustand'
import { ApiContractError, ApiUnavailable, getHealth, getStatus } from '../api/client.ts'
import type { Run, RunStatus } from '../api/types.ts'

export type Connection =
  | { state: 'loading' }
  | {
      state: 'ok'
      lastCheck: string | null
      lastUpdate: string | null
      lastRunStatus: RunStatus | null // null — останній запуск без фінального статусу (або запусків не було)
      recentErrors: Run[]
    }
  | { state: 'unavailable' }
  | { state: 'error'; message: string }

interface ConnectionStore {
  connection: Connection
  check: () => Promise<void>
}

export const useConnection = create<ConnectionStore>((set) => ({
  connection: { state: 'loading' },
  check: async () => {
    set({ connection: { state: 'loading' } })
    // Спершу /health: якщо backend не живий, /status не запитуємо.
    try {
      await getHealth()
    } catch (e) {
      set({ connection: e instanceof ApiContractError ? { state: 'error', message: e.message } : { state: 'unavailable' } })
      return
    }
    try {
      const status = await getStatus()
      set({
        connection: {
          state: 'ok',
          lastCheck: status.last_run?.started_at ?? null,
          lastUpdate: status.last_update?.started_at ?? null,
          lastRunStatus: status.last_run?.status ?? null,
          recentErrors: status.recent_errors,
        },
      })
    } catch (e) {
      if (e instanceof ApiUnavailable) set({ connection: { state: 'unavailable' } })
      else set({ connection: { state: 'error', message: (e as Error).message } })
    }
  },
}))
