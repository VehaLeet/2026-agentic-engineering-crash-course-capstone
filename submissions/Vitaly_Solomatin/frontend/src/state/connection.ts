import { create } from 'zustand'
import { ApiContractError, ApiUnauthorized, ApiUnavailable, getHealth, getStatus } from '../api/client.ts'

export type Connection =
  | { state: 'loading' }
  | { state: 'ok'; lastCheck: string | null; lastUpdate: string | null }
  | { state: 'unauthorized' }
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
    // Спершу /health без кредів: так «backend лежить» ніколи не сплутається з «немає автентифікації».
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
      if (e instanceof ApiUnauthorized) set({ connection: { state: 'unauthorized' } })
      else if (e instanceof ApiUnavailable) set({ connection: { state: 'unavailable' } })
      else set({ connection: { state: 'error', message: (e as Error).message } })
    }
  },
}))
