import { beforeEach, expect, it, vi } from 'vitest'
import * as client from '../api/client.ts'
import { useConnection } from './connection.ts'

vi.mock('../api/client.ts', async (orig) => {
  const actual = await orig<typeof client>()
  return { ...actual, getHealth: vi.fn(), getStatus: vi.fn() }
})

const getHealth = vi.mocked(client.getHealth)
const getStatus = vi.mocked(client.getStatus)

beforeEach(() => {
  vi.resetAllMocks()
  useConnection.setState({ connection: { state: 'loading' } })
})

const state = () => useConnection.getState().connection

it('unavailable when /health fails, and /status is not called', async () => {
  getHealth.mockRejectedValue(new client.ApiUnavailable('HTTP 502'))
  await useConnection.getState().check()
  expect(state()).toEqual({ state: 'unavailable' })
  expect(getStatus).not.toHaveBeenCalled()
})

it('error on contract mismatch', async () => {
  getHealth.mockResolvedValue({ status: 'ok' })
  getStatus.mockRejectedValue(new client.ApiContractError('неочікувана відповідь /status'))
  await useConnection.getState().check()
  expect(state()).toEqual({ state: 'error', message: 'неочікувана відповідь /status' })
})

it('ok with last check and last update times', async () => {
  getHealth.mockResolvedValue({ status: 'ok' })
  getStatus.mockResolvedValue({
    last_run: { id: 5, started_at: '2026-09-28T11:52:38Z', finished_at: null, status: null, trigger: 'manual', changed_days: [], error_message: null },
    last_update: { id: 3, started_at: '2026-09-28T09:00:00Z', finished_at: '2026-09-28T09:00:02Z', status: 'success', trigger: 'manual', changed_days: [], error_message: null },
    recent_errors: [],
  })
  await useConnection.getState().check()
  expect(state()).toEqual({ state: 'ok', lastCheck: '2026-09-28T11:52:38Z', lastUpdate: '2026-09-28T09:00:00Z' })
})

it('ok with nulls on an empty run log', async () => {
  getHealth.mockResolvedValue({ status: 'ok' })
  getStatus.mockResolvedValue({ last_run: null, last_update: null, recent_errors: [] })
  await useConnection.getState().check()
  expect(state()).toEqual({ state: 'ok', lastCheck: null, lastUpdate: null })
})
