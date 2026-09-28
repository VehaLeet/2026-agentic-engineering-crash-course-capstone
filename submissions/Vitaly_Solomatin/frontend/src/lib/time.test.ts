import { expect, it } from 'vitest'
import { formatKyiv } from './time.ts'

it('shows Kyiv summer time (EEST, UTC+3)', () => {
  const s = formatKyiv('2026-09-28T09:00:00Z')
  expect(s).toContain('12:00')
  expect(s).toContain('28.09')
})

it('shows Kyiv winter time (EET, UTC+2)', () => {
  expect(formatKyiv('2026-12-28T09:00:00Z')).toContain('11:00')
})
