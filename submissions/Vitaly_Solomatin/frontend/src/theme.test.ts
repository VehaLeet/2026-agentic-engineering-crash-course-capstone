import { expect, it } from 'vitest'
import { applyTheme, cssVar, palette, type PaletteKey } from './theme.ts'

it('applyTheme writes every palette colour as a CSS variable', () => {
  const root = document.createElement('div')
  applyTheme(root)
  for (const key of Object.keys(palette) as PaletteKey[]) {
    expect(root.style.getPropertyValue(cssVar(key))).toBe(palette[key])
  }
})

// Відносна яскравість і контраст за WCAG 2.x.
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

it.each([
  ['gray900', 'gray50', 7],
  ['navy900', 'white', 7],
  ['gray600', 'white', 4.5],
] as const)('contrast %s on %s >= %d:1', (fg, bg, min) => {
  expect(contrast(palette[fg], palette[bg])).toBeGreaterThanOrEqual(min)
})
