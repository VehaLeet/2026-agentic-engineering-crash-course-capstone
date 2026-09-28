import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as client from '../api/client.ts'
import type { Run } from '../api/types.ts'
import { useCollect } from './collect.ts'
import { useConnection } from './connection.ts'
import { usePrices } from './prices.ts'

vi.mock('../api/client.ts', async (orig) => ({ ...(await orig<typeof client>()), startCollect: vi.fn(), getRun: vi.fn() }))
const startCollect = vi.mocked(client.startCollect)
const getRun = vi.mocked(client.getRun)
const check = vi.fn().mockResolvedValue(undefined)
const load = vi.fn().mockResolvedValue(undefined)

const run = (status: Run['status'], extra: Partial<Run> = {}): Run => ({
  id: 5, started_at: '2026-09-28T10:00:00Z', finished_at: status ? '2026-09-28T10:00:02Z' : null,
  status, trigger: 'manual', changed_days: [], error_message: null, ...extra,
})
const phase = () => useCollect.getState().collect

beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
  check.mockResolvedValue(undefined)
  load.mockResolvedValue(undefined)
  useConnection.setState({ check })
  usePrices.setState({ load })
  useCollect.setState({ collect: { phase: 'idle' } })
  startCollect.mockResolvedValue({ run_id: 5, status_url: '/runs/5' })
})
afterEach(() => vi.useRealTimers())

it('polls once per second until a final status', async () => {
  getRun.mockResolvedValueOnce(run(null)).mockResolvedValueOnce(run(null)).mockResolvedValueOnce(run('no_changes'))
  const p = useCollect.getState().start()
  await vi.advanceTimersByTimeAsync(3000)
  await p
  expect(getRun).toHaveBeenCalledTimes(3)
  expect(phase()).toEqual({ phase: 'done', run: run('no_changes') })
})

it('a second start while running does not start another collection', async () => {
  getRun.mockResolvedValue(run('no_changes'))
  const p1 = useCollect.getState().start()
  const p2 = useCollect.getState().start()
  await vi.advanceTimersByTimeAsync(1000)
  await Promise.all([p1, p2])
  expect(startCollect).toHaveBeenCalledTimes(1)
})

it('gives up after 2 minutes without a final status', async () => {
  getRun.mockResolvedValue(run(null))
  const p = useCollect.getState().start()
  await vi.advanceTimersByTimeAsync(121_000)
  await p
  expect(phase()).toEqual({ phase: 'timeout', runId: 5 })
  const calls = getRun.mock.calls.length
  await vi.advanceTimersByTimeAsync(10_000)
  expect(getRun.mock.calls.length).toBe(calls) // опитування припинилось
})

it('failed when starting or polling hits an unavailable backend', async () => {
  startCollect.mockRejectedValueOnce(new client.ApiUnavailable('HTTP 502'))
  await useCollect.getState().start()
  expect(phase()).toEqual({ phase: 'failed', message: 'Backend недоступний' })

  getRun.mockRejectedValueOnce(new client.ApiUnavailable('HTTP 502'))
  const p = useCollect.getState().start()
  await vi.advanceTimersByTimeAsync(1000)
  await p
  expect(phase()).toEqual({ phase: 'failed', message: 'Backend недоступний' })
})

it('success refreshes status and data; no_changes refreshes status only', async () => {
  getRun.mockResolvedValueOnce(run('success', { changed_days: ['2026-09-29'] }))
  let p = useCollect.getState().start()
  await vi.advanceTimersByTimeAsync(1000)
  await p
  expect(check).toHaveBeenCalledTimes(1)
  expect(load).toHaveBeenCalledTimes(1)

  getRun.mockResolvedValueOnce(run('no_changes'))
  p = useCollect.getState().start()
  await vi.advanceTimersByTimeAsync(1000)
  await p
  expect(check).toHaveBeenCalledTimes(2)
  expect(load).toHaveBeenCalledTimes(1)
})
