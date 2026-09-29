import { create } from 'zustand'
import {
  addRecipient, ApiUnavailable, deleteRecipient, getNotifications, getSchedule,
  listCandidates, listRecipients, putNotifications, putSchedule, setRecipientEnabled, testRecipient,
} from '../api/client.ts'
import type { Candidate, NotificationsSettings, Recipient, Schedule } from '../api/types.ts'

export type Settings =
  | { state: 'loading' }
  | { state: 'unavailable' }
  | { state: 'error'; message: string }
  | { state: 'ok'; schedule: Schedule; notifications: NotificationsSettings; recipients: Recipient[] }

export interface Msg {
  kind: 'ok' | 'error' | 'warning'
  text: string
}

export type Candidates =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'ok'; items: Candidate[] }
  | { state: 'error'; message: string }

type RecipientAction = 'toggle' | 'delete' | 'test'

interface SettingsStore {
  settings: Settings
  pending: { schedule?: boolean; notifications?: boolean; adding?: boolean; recipients: Record<string, RecipientAction> }
  feedback: { schedule?: Msg; notifications?: Msg; adding?: Msg; recipients: Record<string, Msg> }
  candidates: Candidates
  load: () => Promise<void>
  saveSchedule: (value: { enabled: boolean; interval_minutes: number }) => Promise<boolean>
  setNotifications: (enabled: boolean) => Promise<void>
  addRecipient: (chatId: string) => Promise<boolean>
  toggleRecipient: (chatId: string, enabled: boolean) => Promise<void>
  removeRecipient: (chatId: string) => Promise<void>
  testRecipient: (chatId: string) => Promise<void>
  findCandidates: () => Promise<void>
  addCandidate: (chatId: string) => Promise<void>
}

export const errorText = (e: unknown): string =>
  e instanceof ApiUnavailable ? 'Backend недоступний' : (e as Error).message

const error = (e: unknown): Msg => ({ kind: 'error', text: errorText(e) })

// Для кандидатів 502 з поясненням backend (збій Telegram) важливіший за загальне «Backend недоступний».
const candidatesErrorText = (e: unknown): string =>
  e instanceof ApiUnavailable && !/^(HTTP \d+$|мережева помилка)/.test(e.message) ? e.message : errorText(e)

const initial = {
  settings: { state: 'loading' } as Settings,
  pending: { recipients: {} },
  feedback: { recipients: {} },
  candidates: { state: 'idle' } as Candidates, // запит у Telegram — лише за натисканням
}

export const useSettings = create<SettingsStore>((set, get) => {
  const patch = (fn: (s: Extract<Settings, { state: 'ok' }>) => Partial<Extract<Settings, { state: 'ok' }>>) => {
    const s = get().settings
    if (s.state === 'ok') set({ settings: { ...s, ...fn(s) } })
  }
  const pendingRecipient = (chatId: string, action?: RecipientAction) => {
    const recipients = { ...get().pending.recipients }
    if (action) recipients[chatId] = action
    else delete recipients[chatId]
    set({ pending: { ...get().pending, recipients } })
  }
  const recipientMsg = (chatId: string, msg?: Msg) => {
    const recipients = { ...get().feedback.recipients }
    if (msg) recipients[chatId] = msg
    else delete recipients[chatId]
    set({ feedback: { ...get().feedback, recipients } })
  }
  // Після кожної зміни переліку показуємо стан сервера: дублікати й чужі видалення вирішуються самі.
  const reloadRecipients = async () => {
    const recipients = await listRecipients()
    patch(() => ({ recipients }))
  }

  return {
    ...initial,

    load: async () => {
      set({ ...initial, settings: { state: 'loading' } })
      try {
        const [schedule, notifications, recipients] = await Promise.all([getSchedule(), getNotifications(), listRecipients()])
        set({ settings: { state: 'ok', schedule, notifications, recipients } })
      } catch (e) {
        set({ settings: e instanceof ApiUnavailable ? { state: 'unavailable' } : { state: 'error', message: errorText(e) } })
      }
    },

    saveSchedule: async (value) => {
      set({ pending: { ...get().pending, schedule: true }, feedback: { ...get().feedback, schedule: undefined } })
      try {
        const schedule = await putSchedule(value)
        patch(() => ({ schedule }))
        set({ feedback: { ...get().feedback, schedule: { kind: 'ok', text: 'Розклад збережено' } } })
        return true
      } catch (e) {
        set({ feedback: { ...get().feedback, schedule: error(e) } })
        return false
      } finally {
        set({ pending: { ...get().pending, schedule: false } })
      }
    },

    setNotifications: async (enabled) => {
      set({ pending: { ...get().pending, notifications: true }, feedback: { ...get().feedback, notifications: undefined } })
      try {
        const notifications = await putNotifications(enabled)
        patch(() => ({ notifications }))
      } catch (e) {
        set({ feedback: { ...get().feedback, notifications: error(e) } }) // значення не змінилось — це і є «повернення»
      } finally {
        set({ pending: { ...get().pending, notifications: false } })
      }
    },

    addRecipient: async (chatId) => {
      set({ pending: { ...get().pending, adding: true }, feedback: { ...get().feedback, adding: undefined } })
      try {
        await addRecipient(chatId)
        await reloadRecipients()
        return true
      } catch (e) {
        set({ feedback: { ...get().feedback, adding: error(e) } })
        return false
      } finally {
        set({ pending: { ...get().pending, adding: false } })
      }
    },

    toggleRecipient: async (chatId, enabled) => {
      pendingRecipient(chatId, 'toggle')
      recipientMsg(chatId)
      try {
        await setRecipientEnabled(chatId, enabled)
        await reloadRecipients()
      } catch (e) {
        recipientMsg(chatId, error(e))
      } finally {
        pendingRecipient(chatId)
      }
    },

    removeRecipient: async (chatId) => {
      pendingRecipient(chatId, 'delete')
      recipientMsg(chatId)
      try {
        await deleteRecipient(chatId).catch((e) => {
          if ((e as { status?: number }).status !== 404) throw e // 404: вже видалено деінде — мета досягнута
        })
        await reloadRecipients()
      } catch (e) {
        recipientMsg(chatId, error(e))
      } finally {
        pendingRecipient(chatId)
      }
    },

    findCandidates: async () => {
      set({ candidates: { state: 'loading' } })
      try {
        set({ candidates: { state: 'ok', items: await listCandidates() } })
      } catch (e) {
        set({ candidates: { state: 'error', message: candidatesErrorText(e) } })
      }
    },

    addCandidate: async (chatId) => {
      // Той самий шлях, що й ручне введення; позначки added рахує сервер — тому пошук повторюється.
      if (await get().addRecipient(chatId)) await get().findCandidates()
    },

    testRecipient: async (chatId) => {
      pendingRecipient(chatId, 'test')
      recipientMsg(chatId)
      try {
        const result = await testRecipient(chatId)
        recipientMsg(chatId, result.ok
          ? { kind: 'ok', text: 'Тестове повідомлення надіслано' }
          : { kind: 'warning', text: result.error ?? 'Telegram відхилив повідомлення' })
      } catch (e) {
        recipientMsg(chatId, error(e))
      } finally {
        pendingRecipient(chatId)
      }
    },
  }
})
