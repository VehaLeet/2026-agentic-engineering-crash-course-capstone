import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../api/prices.ts'
import { ApiUnavailable, ApiValidationError } from '../api/client.ts'
import { usePrices } from './prices.ts'
import { daily, hourly } from '../test/prices-fixtures.ts'

vi.mock('../api/prices.ts', async (orig) => ({ ...(await orig<typeof api>()), getPrices: vi.fn() }))
const getPrices = vi.mocked(api.getPrices)
const state = () => usePrices.getState()

beforeEach(() => {
  vi.resetAllMocks()
  usePrices.setState({ range: { from: '2026-09-23', to: '2026-09-29' }, resolution: 'hour', prices: { state: 'loading' } })
})

it('ok with data', async () => {
  getPrices.mockResolvedValue(hourly())
  await state().load()
  expect(state().prices).toEqual({ state: 'ok', data: hourly() })
})

it('empty arrays -> empty, not ok or error', async () => {
  getPrices.mockResolvedValue({ ...hourly(), delivery_date: [], period: [], price: [], volume_sell: [], volume_buy: [], declared_volume_sell: [], declared_volume_buy: [] })
  await state().load()
  expect(state().prices).toEqual({ state: 'empty' })
})

it('unavailable, invalid (422) and error states', async () => {
  getPrices.mockRejectedValueOnce(new ApiUnavailable('HTTP 502'))
  await state().load()
  expect(state().prices).toEqual({ state: 'unavailable' })
  getPrices.mockRejectedValueOnce(new ApiValidationError('bad range'))
  await state().load()
  expect(state().prices).toEqual({ state: 'invalid', message: 'bad range' })
  getPrices.mockRejectedValueOnce(new Error('boom'))
  await state().load()
  expect(state().prices.state).toBe('error')
})

it('inverted range is rejected without a request', async () => {
  usePrices.setState({ range: { from: '2026-09-29', to: '2026-09-23' } })
  await state().load()
  expect(getPrices).not.toHaveBeenCalled()
  expect(state().prices).toEqual({ state: 'invalid', message: 'Початкова дата пізніша за кінцеву' })
})

it('hourly is refused for > 366 days without a request', async () => {
  getPrices.mockResolvedValue(daily())
  state().setRange({ from: '2024-01-01', to: '2025-01-01' }) // 367 діб
  expect(state().resolution).toBe('day')
  state().setResolution('hour')
  expect(state().resolution).toBe('day')
  await vi.waitFor(() => expect(getPrices).toHaveBeenCalled())
  expect(getPrices.mock.calls.every(([, r]) => r === 'day')).toBe(true)
})

it('"all history" preset switches to daily', async () => {
  getPrices.mockResolvedValue(daily())
  state().setPreset('all')
  expect(state().range.from).toBe('2019-07-01')
  expect(state().resolution).toBe('day')
})

it('a stale response never overwrites a newer one', async () => {
  let resolveFirst!: (v: api.Prices) => void
  getPrices
    .mockImplementationOnce(() => new Promise((r) => { resolveFirst = r }))
    .mockResolvedValueOnce(daily())
  const first = state().load()
  usePrices.setState({ resolution: 'day' })
  await state().load() // другий запит завершився першим
  resolveFirst(hourly()) // перший приходить пізніше
  await first
  expect(state().prices).toEqual({ state: 'ok', data: daily() })
})

it('presets set their own resolution: "Рік" after "Уся історія" is hourly again', () => {
  getPrices.mockResolvedValue(daily())
  state().setPreset('all')
  expect(state().resolution).toBe('day')
  state().setPreset('year')
  expect(state().resolution).toBe('hour')
  expect(getPrices.mock.calls.at(-1)?.[1]).toBe('hour')
})
