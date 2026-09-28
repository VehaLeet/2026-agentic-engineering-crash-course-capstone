import { create } from 'zustand'
import { ApiUnavailable, getRun, startCollect } from '../api/client.ts'
import type { Run } from '../api/types.ts'
import { useConnection } from './connection.ts'
import { usePrices } from './prices.ts'

export const POLL_INTERVAL_MS = 1000
export const POLL_DEADLINE_MS = 120_000 // найгірший збір ~90 с (3 спроби по 30 с)

export type Collect =
  | { phase: 'idle' }
  | { phase: 'running'; runId?: number }
  | { phase: 'done'; run: Run }
  | { phase: 'timeout'; runId: number }
  | { phase: 'failed'; message: string }

interface CollectStore {
  collect: Collect
  start: () => Promise<void>
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function failure(e: unknown): Collect {
  return { phase: 'failed', message: e instanceof ApiUnavailable ? 'Backend недоступний' : (e as Error).message }
}

export const useCollect = create<CollectStore>((set, get) => ({
  collect: { phase: 'idle' },
  start: async () => {
    if (get().collect.phase === 'running') return // захист від подвійного кліку
    set({ collect: { phase: 'running' } })
    let runId: number
    try {
      runId = (await startCollect()).run_id
    } catch (e) {
      set({ collect: failure(e) })
      return
    }
    set({ collect: { phase: 'running', runId } })
    const deadline = Date.now() + POLL_DEADLINE_MS
    // Цикл «зачекати -> запит», а не setInterval: запити не нашаровуються, якщо API повільний.
    for (;;) {
      await sleep(POLL_INTERVAL_MS)
      let run: Run
      try {
        run = await getRun(runId)
      } catch (e) {
        set({ collect: failure(e) })
        return
      }
      if (run.status !== null) {
        set({ collect: { phase: 'done', run } })
        void useConnection.getState().check()
        if (run.status === 'success') void usePrices.getState().load()
        return
      }
      if (Date.now() >= deadline) {
        set({ collect: { phase: 'timeout', runId } })
        return
      }
    }
  },
}))
