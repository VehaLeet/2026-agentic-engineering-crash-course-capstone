/** Єдине джерело палітри industrial. CSS-змінні записує applyTheme() — index.css їх лише використовує. */
export const palette = {
  navy900: '#0b1f3a', // шапка, основні кнопки, головна серія графіка
  navy700: '#13315c', // hover, друга серія
  navy400: '#5a7ba6', // допоміжні серії (мін/макс), стовпці обсягу
  white: '#ffffff',
  gray50: '#f4f6f8', // фон сторінки, зебра таблиці
  gray300: '#cfd6de', // рамки, сітка графіка
  gray600: '#5b6675', // другорядний текст, підписи осей
  gray900: '#1f2733', // основний текст
} as const

export type PaletteKey = keyof typeof palette

/** CSS-змінна для ключа палітри: navy900 -> --color-navy-900. */
export function cssVar(key: PaletteKey): string {
  return `--color-${key.replace(/(\d+)$/, '-$1')}`
}

/** Записати палітру в CSS-змінні :root. Викликається один раз при старті застосунку. */
export function applyTheme(root: HTMLElement = document.documentElement): void {
  for (const key of Object.keys(palette) as PaletteKey[]) root.style.setProperty(cssVar(key), palette[key])
}
