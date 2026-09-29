import { INTERVAL_MAX, INTERVAL_MIN } from '../api/types.ts'

/** Помилка поля інтервалу або null. Ті самі межі перевіряє бекенд. */
export function intervalError(raw: string): string | null {
  const n = Number(raw)
  if (raw.trim() === '' || !Number.isInteger(n) || n < INTERVAL_MIN || n > INTERVAL_MAX) {
    return `Ціле число хвилин від ${INTERVAL_MIN} до ${INTERVAL_MAX}`
  }
  return null
}
