import { expect, it } from 'vitest'
import { palette } from '../../theme.ts'
import { daily, hourly } from '../../test/prices-fixtures.ts'
import { buildChartOption } from './buildChartOption.ts'

type S = { name: string; type: string; data: unknown[]; color: string; sampling?: string; yAxisIndex: number }
const series = (o: ReturnType<typeof buildChartOption>) => o.series as S[]

it('hourly: price line and sell-volume bars, 24 points each, two Y axes', () => {
  const o = buildChartOption(hourly())
  const [price, volume] = series(o)
  expect([price.type, volume.type]).toEqual(['line', 'bar'])
  expect(price.data).toHaveLength(24)
  expect(volume.data).toHaveLength(24)
  expect([price.yAxisIndex, volume.yAxisIndex]).toEqual([0, 1])
  expect(o.yAxis as unknown[]).toHaveLength(2)
})

it('hourly x labels are Kyiv time, independent of browser TZ', () => {
  const labels = (buildChartOption(hourly()).xAxis as { data: string[] }).data
  expect(labels[12]).toBe('28.09 12:00')
})

it('daily: weighted, min, max and volume; null stays null (a gap, not zero)', () => {
  const s = series(buildChartOption(daily()))
  expect(s.map((x) => x.name)).toEqual(['Зважена ціна', 'Мінімум', 'Максимум', 'Обсяг продажу'])
  expect(s[0].data).toEqual([6560.6, null])
})

it('series colours come from the theme palette', () => {
  const allowed = new Set(Object.values(palette))
  for (const d of [hourly(), daily()]) {
    for (const s of series(buildChartOption(d))) expect(allowed.has(s.color as never), s.name).toBe(true)
  }
})

it('long series: lttb sampling and no animation; short: animated', () => {
  const long = buildChartOption(hourly('2026-09-28', 24 * 50))
  expect(long.animation).toBe(false)
  expect(series(long)[0].sampling).toBe('lttb')
  const short = buildChartOption(hourly())
  expect(short.animation).toBe(true)
  expect(series(short)[0].sampling).toBeUndefined()
})
