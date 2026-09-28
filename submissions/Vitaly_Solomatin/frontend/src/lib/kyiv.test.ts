import { describe, expect, it } from 'vitest'
import { hourlyLabels, kyivTime, kyivToday, periodStart, presetRange, rangeDays } from './kyiv.ts'

const at = (date: string, p: number) => kyivTime(periodStart(date, p))

describe(`periodStart (browser TZ=${Intl.DateTimeFormat().resolvedOptions().timeZone})`, () => {
  it('regular day', () => {
    expect(at('2026-09-28', 1)).toBe('00:00')
    expect(at('2026-09-28', 13)).toBe('12:00')
  })

  it('spring DST day (23 periods): 03:00 does not exist', () => {
    expect(at('2025-03-30', 3)).toBe('02:00')
    expect(at('2025-03-30', 4)).toBe('04:00')
    expect(at('2025-03-30', 23)).toBe('23:00')
  })

  it('autumn DST day (25 periods): 03:00 happens twice', () => {
    expect(at('2025-10-26', 4)).toBe('03:00')
    expect(at('2025-10-26', 5)).toBe('03:00')
    expect(periodStart('2025-10-26', 5).getTime() - periodStart('2025-10-26', 4).getTime()).toBe(3_600_000)
    expect(at('2025-10-26', 25)).toBe('23:00')
  })

  it('period 13 on 28.09.2026 is 12:00 Kyiv = 09:00Z', () => {
    expect(periodStart('2026-09-28', 13).toISOString()).toBe('2026-09-28T09:00:00.000Z')
  })
})

describe('hourlyLabels', () => {
  it('marks the repeated hour with the period number', () => {
    const periods = Array.from({ length: 25 }, (_, i) => i + 1)
    const labels = hourlyLabels(periods.map(() => '2025-10-26'), periods)
    expect(labels).toHaveLength(25)
    expect(new Set(labels).size).toBe(25)
    expect(labels[3]).toBe('26.10 03:00 (п.4)')
    expect(labels[4]).toBe('26.10 03:00 (п.5)')
    expect(labels[0]).toBe('26.10 00:00')
  })
})

describe('ranges', () => {
  const today = kyivToday(new Date('2026-09-28T09:00:00Z'))

  it('today is taken in Kyiv', () => {
    expect(today).toBe('2026-09-28')
    expect(kyivToday(new Date('2026-09-30T22:30:00Z'))).toBe('2026-10-01')
  })

  it('default 7 days end tomorrow', () => {
    expect(presetRange('7d', today)).toEqual({ from: '2026-09-23', to: '2026-09-29' })
  })

  it('year preset is exactly the 366-day hourly limit', () => {
    const r = presetRange('year', today)
    expect(rangeDays(r.from, r.to)).toBe(366)
  })

  it('all history starts at market launch', () => {
    expect(presetRange('all', today).from).toBe('2019-07-01')
  })
})
