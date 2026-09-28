import { create } from 'zustand'
import { ApiContractError, ApiUnavailable, getHealth, getStatus } from '../api/client.ts'

export type Connection =
  | { state: 'loading' }
  | { state: 'ok'; lastCheck: string | null; lastUpdate: string | null }
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
        },
      })
    } catch (e) {
      if (e instanceof ApiUnavailable) set({ connection: { state: 'unavailable' } })
      else set({ connection: { state: 'error', message: (e as Error).message } })
    }
  },
}))
