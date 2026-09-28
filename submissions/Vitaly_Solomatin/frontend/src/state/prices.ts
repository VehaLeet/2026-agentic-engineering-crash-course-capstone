import { create } from 'zustand'
import { ApiContractError, ApiUnavailable, ApiValidationError } from '../api/client.ts'
import { getPrices, rowCount, type Prices } from '../api/prices.ts'
import { HOURLY_LIMIT_DAYS, kyivToday, PRESET_RESOLUTION, presetRange, rangeDays, type PresetId, type Range, type Resolution } from '../lib/kyiv.ts'

export type PricesState =
  | { state: 'loading' }
  | { state: 'ok'; data: Prices }
  | { state: 'empty' }
  | { state: 'unavailable' }
  | { state: 'invalid'; message: string }
  | { state: 'error'; message: string }

interface PricesStore {
  range: Range
  resolution: Resolution
  prices: PricesState
  setPreset: (preset: PresetId) => void
  setRange: (range: Range) => void
  setResolution: (resolution: Resolution) => void
  load: () => Promise<void>
}

export function hourlyAllowed(range: Range): boolean {
  return rangeDays(range.from, range.to) <= HOURLY_LIMIT_DAYS
}

// Номер останнього запиту: відповідь застосовується, лише якщо вона на останній запит.
let latest = 0
// Момент початку останнього load() — для заміру «від вибору до графіка» (лише журнал у dev).
let loadStartedAt = 0
export const lastLoadStartedAt = () => loadStartedAt

export const usePrices = create<PricesStore>((set, get) => ({
  range: presetRange('7d', kyivToday()),
  resolution: 'hour',
  prices: { state: 'loading' },

  setPreset: (preset) => {
    // Пресет задає і діапазон, і роздільність — інакше «Рік» після «Уся історія» лишився б подобовим.
    set({ range: presetRange(preset, kyivToday()), resolution: PRESET_RESOLUTION[preset] })
    void get().load()
  },

  setRange: (range) => {
    // Задовгий діапазон не буває погодинним: UI не надсилає запиту, який API відхилить.
    set({ range, resolution: hourlyAllowed(range) ? get().resolution : 'day' })
    void get().load()
  },

  setResolution: (resolution) => {
    if (resolution === 'hour' && !hourlyAllowed(get().range)) return
    set({ resolution })
    void get().load()
  },

  load: async () => {
    const { range, resolution } = get()
    const id = ++latest
    loadStartedAt = performance.now()
    if (range.from > range.to) {
      set({ prices: { state: 'invalid', message: 'Початкова дата пізніша за кінцеву' } })
      return
    }
    if (resolution === 'hour' && !hourlyAllowed(range)) {
      set({ prices: { state: 'invalid', message: `Погодинно — не більше ${HOURLY_LIMIT_DAYS} діб` } })
      return
    }
    set({ prices: { state: 'loading' } })
    let next: PricesState
    try {
      const data = await getPrices(range, resolution)
      next = rowCount(data) === 0 ? { state: 'empty' } : { state: 'ok', data }
    } catch (e) {
      if (e instanceof ApiUnavailable) next = { state: 'unavailable' }
      else if (e instanceof ApiValidationError) next = { state: 'invalid', message: e.message }
      else next = { state: 'error', message: e instanceof ApiContractError ? e.message : String(e) }
    }
    if (id === latest) set({ prices: next })
  },
}))
