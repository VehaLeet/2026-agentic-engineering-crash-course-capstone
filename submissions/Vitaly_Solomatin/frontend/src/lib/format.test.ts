import { expect, it } from 'vitest'
import { formatPrice, formatVolume } from './format.ts'

const norm = (s: string) => s.replace(/\s/g, ' ') // uk-UA групує нерозривним пробілом

it('formats uk-UA numbers like the source precision', () => {
  expect(norm(formatPrice(14947.8))).toBe('14 947,80')
  expect(norm(formatVolume(3246.2))).toBe('3 246,2')
})

it('shows a dash, not zero, for missing values', () => {
  expect(formatPrice(null)).toBe('—')
  expect(formatVolume(null)).toBe('—')
})
