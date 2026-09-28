const price = new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const volume = new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/** Ціна з двома знаками, як у джерелі; порожнє значення — «—», а не 0. */
export function formatPrice(value: number | null): string {
  return value === null ? '—' : price.format(value)
}

/** Обсяг з одним знаком, як у джерелі. */
export function formatVolume(value: number | null): string {
  return value === null ? '—' : volume.format(value)
}
