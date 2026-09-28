/**
 * Дати й час за Europe/Kyiv незалежно від часового поясу браузера.
 * Дата постачання — рядок YYYY-MM-DD; період — порядкова година торгової доби (1..25).
 */

const TZ = 'Europe/Kyiv'
const HOUR = 3_600_000
const DAY = 86_400_000

const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' })
const offsetFmt = new Intl.DateTimeFormat('en-US', { timeZone: TZ, timeZoneName: 'longOffset' })
const parts = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})

export const HISTORY_START = '2019-07-01' // запуск РДН
export const HOURLY_LIMIT_DAYS = 366

/** Сьогоднішня дата за Києвом. */
export function kyivToday(now: Date = new Date()): string {
  return ymd.format(now)
}

export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d) + days * DAY).toISOString().slice(0, 10)
}

/** Кількість діб у діапазоні включно з обома межами. */
export function rangeDays(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00Z`) - Date.parse(`${from}T00:00Z`)) / DAY) + 1
}

/** Зсув Києва від UTC у хвилинах у момент ms (напр. +180 влітку, +120 взимку). */
function kyivOffsetMinutes(ms: number): number {
  const name = offsetFmt.formatToParts(ms).find((p) => p.type === 'timeZoneName')?.value ?? 'GMT'
  const m = /GMT([+-])(\d{2}):(\d{2})/.exec(name)
  return m ? (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0
}

/** Момент опівночі за Києвом на дату. Опівніч ніколи не припадає на перехід (він о 03:00/04:00). */
export function kyivMidnight(date: string): number {
  const [y, m, d] = date.split('-').map(Number)
  const utcMidnight = Date.UTC(y, m - 1, d)
  let t = utcMidnight - kyivOffsetMinutes(utcMidnight) * 60_000
  const corrected = utcMidnight - kyivOffsetMinutes(t) * 60_000
  if (corrected !== t) t = corrected
  return t
}

/** Початок періоду: опівніч за Києвом + (період − 1) реальних годин. Коректно для 23/25-годинних діб. */
export function periodStart(date: string, period: number): Date {
  return new Date(kyivMidnight(date) + (period - 1) * HOUR)
}

/** «HH:MM» за Києвом. */
export function kyivTime(instant: Date): string {
  const p = Object.fromEntries(parts.formatToParts(instant).map((x) => [x.type, x.value]))
  return `${p.hour}:${p.minute}`
}

function shortDate(date: string): string {
  const [, m, d] = date.split('-')
  return `${d}.${m}`
}

/**
 * Підписи погодинної осі: «DD.MM HH:00». Коли година в межах доби повторюється
 * (доба переходу на зимовий час), до підпису додається номер періоду.
 */
export function hourlyLabels(dates: string[], periods: number[]): string[] {
  const base = dates.map((d, i) => `${shortDate(d)} ${kyivTime(periodStart(d, periods[i]))}`)
  const count = new Map<string, number>()
  for (const b of base) count.set(b, (count.get(b) ?? 0) + 1)
  return base.map((b, i) => (count.get(b)! > 1 ? `${b} (п.${periods[i]})` : b))
}

/** Підпис подобової осі: «DD.MM.YY». */
export function dailyLabel(date: string): string {
  const [y, m, d] = date.split('-')
  return `${d}.${m}.${y.slice(2)}`
}

export type Resolution = 'hour' | 'day'
export interface Range {
  from: string
  to: string
}
export type PresetId = '7d' | '30d' | 'year' | 'all'

/** Роздільність пресету (design.md): лише «Уся історія» подобова, решта в межах погодинного ліміту. */
export const PRESET_RESOLUTION: Record<PresetId, Resolution> = { '7d': 'hour', '30d': 'hour', year: 'hour', all: 'day' }

/** Пресети закінчуються завтрашньою добою: результати на завтра публікуються сьогодні. */
export function presetRange(preset: PresetId, today: string): Range {
  const to = addDays(today, 1)
  switch (preset) {
    case '7d':
      return { from: addDays(to, -6), to }
    case '30d':
      return { from: addDays(to, -29), to }
    case 'year':
      return { from: addDays(to, -(HOURLY_LIMIT_DAYS - 1)), to }
    case 'all':
      return { from: HISTORY_START, to }
  }
}
