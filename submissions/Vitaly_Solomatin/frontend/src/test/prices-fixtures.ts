import type { PricesDaily, PricesHourly } from '../api/prices.ts'

/** Погодинна доба з n періодами (форма реальної відповіді /prices?resolution=hour). */
export function hourly(date = '2026-09-28', n = 24): PricesHourly {
  const idx = Array.from({ length: n }, (_, i) => i)
  return {
    resolution: 'hour',
    delivery_date: idx.map(() => date),
    period: idx.map((i) => i + 1),
    price: idx.map((i) => 5000 + i * 100),
    volume_sell: idx.map(() => 3000.5),
    volume_buy: idx.map(() => 3000.5),
    declared_volume_sell: idx.map(() => 4000.1),
    declared_volume_buy: idx.map(() => 3100.2),
  }
}

/** Реальні подобові числа ОРЕЕ за 26.09.2026 + доба без зваженої ціни. */
export function daily(): PricesDaily {
  return {
    resolution: 'day',
    delivery_date: ['2026-09-26', '2026-09-27'],
    price_min: [15, 50],
    price_max: [14968.9, 12000],
    price_avg: [6301.37, 5000],
    price_weighted: [6560.6, null],
    volume_sell: [72279.5, 0],
    volume_buy: [72279.5, 0],
    declared_volume_sell: [114287.9, 1],
    declared_volume_buy: [74232.5, 1],
    periods: [24, 24],
  }
}
