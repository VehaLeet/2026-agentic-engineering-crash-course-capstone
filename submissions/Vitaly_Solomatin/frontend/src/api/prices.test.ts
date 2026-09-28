import { afterEach, expect, it, vi } from 'vitest'
import { ApiContractError, ApiUnavailable, ApiValidationError } from './client.ts'
import { getPrices } from './prices.ts'
import { daily, hourly } from '../test/prices-fixtures.ts'

const range = { from: '2026-09-28', to: '2026-09-28' }

function respond(status: number, body?: unknown) {
  const f = vi.fn().mockResolvedValue(new Response(body === undefined ? null : JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', f)
  return f
}
afterEach(() => vi.unstubAllGlobals())

it('requests /api/prices with range and resolution', async () => {
  const f = respond(200, hourly())
  await expect(getPrices(range, 'hour')).resolves.toEqual(hourly())
  expect(f.mock.calls[0][0]).toBe('/api/prices?date_from=2026-09-28&date_to=2026-09-28&resolution=hour')
})

it('accepts the daily contract including null weighted price', async () => {
  respond(200, daily())
  await expect(getPrices(range, 'day')).resolves.toEqual(daily())
})

it('422 -> ApiValidationError with API detail', async () => {
  respond(422, { detail: 'hourly range is limited to 366 days; use resolution=day' })
  const e = await getPrices(range, 'hour').catch((x) => x)
  expect(e).toBeInstanceOf(ApiValidationError)
  expect(e.message).toContain('resolution=day')
})

it('502 -> ApiUnavailable', async () => {
  respond(502)
  await expect(getPrices(range, 'hour')).rejects.toBeInstanceOf(ApiUnavailable)
})

it('columns of different length -> ApiContractError', async () => {
  respond(200, { ...hourly(), price: [1, 2] })
  await expect(getPrices(range, 'hour')).rejects.toBeInstanceOf(ApiContractError)
})

it('wrong resolution in body -> ApiContractError', async () => {
  respond(200, daily())
  await expect(getPrices(range, 'hour')).rejects.toBeInstanceOf(ApiContractError)
})
