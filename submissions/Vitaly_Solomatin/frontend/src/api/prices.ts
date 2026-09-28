import type { Range, Resolution } from '../lib/kyiv.ts'
import { ApiContractError, request } from './client.ts'

// Колонковий контракт GET /prices (openspec/specs/prices-api): кожне поле — масив однакової довжини.
export interface PricesHourly {
  resolution: 'hour'
  delivery_date: string[]
  period: number[]
  price: number[]
  volume_sell: number[]
  volume_buy: number[]
  declared_volume_sell: number[]
  declared_volume_buy: number[]
}

export interface PricesDaily {
  resolution: 'day'
  delivery_date: string[]
  price_min: number[]
  price_max: number[]
  price_avg: number[] // проста середня (BASE)
  price_weighted: (number | null)[] // зважена за обсягом продажу (= «середньозважена» ОРЕЕ)
  volume_sell: number[]
  volume_buy: number[]
  declared_volume_sell: number[]
  declared_volume_buy: number[]
  periods: number[]
}

export type Prices = PricesHourly | PricesDaily

const COLUMNS: Record<Resolution, string[]> = {
  hour: ['delivery_date', 'period', 'price', 'volume_sell', 'volume_buy', 'declared_volume_sell', 'declared_volume_buy'],
  day: ['delivery_date', 'price_min', 'price_max', 'price_avg', 'price_weighted', 'volume_sell', 'volume_buy',
    'declared_volume_sell', 'declared_volume_buy', 'periods'],
}

export async function getPrices(range: Range, resolution: Resolution): Promise<Prices> {
  const q = new URLSearchParams({ date_from: range.from, date_to: range.to, resolution })
  const body = (await request(`/prices?${q}`)) as Record<string, unknown> | null
  if (!body || body.resolution !== resolution) throw new ApiContractError('неочікувана відповідь /prices')
  const lengths = COLUMNS[resolution].map((c) => (Array.isArray(body[c]) ? (body[c] as unknown[]).length : -1))
  if (lengths.includes(-1) || new Set(lengths).size !== 1) {
    throw new ApiContractError('неочікувана відповідь /prices: колонки відсутні або різної довжини')
  }
  return body as unknown as Prices
}

export function rowCount(data: Prices): number {
  return data.delivery_date.length
}
