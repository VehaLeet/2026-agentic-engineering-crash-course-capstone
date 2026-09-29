import { beforeEach, expect, it, vi } from 'vitest'
import * as client from '../api/client.ts'
import { ApiRequestError, ApiUnavailable, ApiValidationError } from '../api/client.ts'
import type { Recipient, Schedule } from '../api/types.ts'
import { useSettings } from './settings.ts'

vi.mock('../api/client.ts', async (orig) => ({
  ...(await orig<typeof client>()),
  getSchedule: vi.fn(), putSchedule: vi.fn(), getNotifications: vi.fn(), putNotifications: vi.fn(),
  listRecipients: vi.fn(), addRecipient: vi.fn(), setRecipientEnabled: vi.fn(), deleteRecipient: vi.fn(),
  testRecipient: vi.fn(), listCandidates: vi.fn(),
}))
const api = vi.mocked(client)

const SCHEDULE: Schedule = { enabled: true, interval_minutes: 60, next_run_at: '2026-09-29T09:00:00Z' }
const NOTIFICATIONS = { enabled: true, token_configured: true }
const R = (chat_id: string, enabled = true): Recipient => ({ chat_id, enabled })
const s = () => useSettings.getState()
const ok = () => {
  const st = s().settings
  if (st.state !== 'ok') throw new Error(`state ${st.state}`)
  return st
}

beforeEach(async () => {
  vi.resetAllMocks()
  useSettings.setState({ settings: { state: 'loading' }, pending: { recipients: {} }, feedback: { recipients: {} } })
  api.getSchedule.mockResolvedValue(SCHEDULE)
  api.getNotifications.mockResolvedValue(NOTIFICATIONS)
  api.listRecipients.mockResolvedValue([R('123')])
})

// load

it('loads all three resources', async () => {
  await s().load()
  expect(ok()).toEqual({ state: 'ok', schedule: SCHEDULE, notifications: NOTIFICATIONS, recipients: [R('123')] })
})

it('backend down -> unavailable; other failure -> error', async () => {
  api.getSchedule.mockRejectedValue(new ApiUnavailable('HTTP 502'))
  await s().load()
  expect(s().settings).toEqual({ state: 'unavailable' })
  api.getSchedule.mockRejectedValue(new client.ApiContractError('неочікувана відповідь'))
  await s().load()
  expect(s().settings).toEqual({ state: 'error', message: 'неочікувана відповідь' })
})

it('is loading while requests are in flight', async () => {
  let release!: () => void
  api.getSchedule.mockReturnValue(new Promise((r) => { release = () => r(SCHEDULE) }))
  const p = s().load()
  expect(s().settings).toEqual({ state: 'loading' })
  release()
  await p
  expect(s().settings.state).toBe('ok')
})

// schedule & notifications

it('saveSchedule sends the value and shows the server response', async () => {
  await s().load()
  const saved = { enabled: true, interval_minutes: 15, next_run_at: '2026-09-29T08:30:00Z' }
  let release!: () => void
  api.putSchedule.mockReturnValue(new Promise((r) => { release = () => r(saved) }))
  const p = s().saveSchedule({ enabled: true, interval_minutes: 15 })
  expect(s().pending.schedule).toBe(true)
  release()
  expect(await p).toBe(true)
  expect(api.putSchedule).toHaveBeenCalledWith({ enabled: true, interval_minutes: 15 })
  expect(ok().schedule).toEqual(saved)
  expect(s().pending.schedule).toBe(false)
})

it('saveSchedule failure keeps the stored schedule and explains why', async () => {
  await s().load()
  api.putSchedule.mockRejectedValue(new ApiValidationError('interval out of range'))
  expect(await s().saveSchedule({ enabled: true, interval_minutes: 15 })).toBe(false)
  expect(ok().schedule).toEqual(SCHEDULE)
  expect(s().feedback.schedule).toEqual({ kind: 'error', text: 'interval out of range' })
  api.putSchedule.mockRejectedValue(new ApiUnavailable('мережева помилка'))
  await s().saveSchedule({ enabled: true, interval_minutes: 15 })
  expect(s().feedback.schedule?.text).toBe('Backend недоступний')
})

it('setNotifications updates only after the server answers, reverts on failure', async () => {
  await s().load()
  api.putNotifications.mockResolvedValue({ enabled: false, token_configured: true })
  await s().setNotifications(false)
  expect(api.putNotifications).toHaveBeenCalledWith(false)
  expect(ok().notifications.enabled).toBe(false)
  api.putNotifications.mockRejectedValue(new ApiUnavailable('x'))
  await s().setNotifications(true)
  expect(ok().notifications.enabled).toBe(false)
  expect(s().feedback.notifications).toEqual({ kind: 'error', text: 'Backend недоступний' })
  expect(s().pending.notifications).toBe(false)
})

// recipients

it('add reloads the list from the server (no client-side duplicates)', async () => {
  await s().load()
  api.addRecipient.mockResolvedValue(R('123'))
  api.listRecipients.mockResolvedValue([R('123')])
  expect(await s().addRecipient('123')).toBe(true)
  expect(ok().recipients).toEqual([R('123')])
})

it('add rejected with 422 leaves the list and shows the server detail', async () => {
  await s().load()
  api.addRecipient.mockRejectedValue(new ApiValidationError('некоректний chat_id'))
  expect(await s().addRecipient('hello world')).toBe(false)
  expect(ok().recipients).toEqual([R('123')])
  expect(s().feedback.adding).toEqual({ kind: 'error', text: 'некоректний chat_id' })
  expect(api.listRecipients).toHaveBeenCalledTimes(1)
})

it('toggle sends the new value and shows the reloaded state', async () => {
  await s().load()
  api.setRecipientEnabled.mockResolvedValue(R('123', false))
  api.listRecipients.mockResolvedValue([R('123', false)])
  await s().toggleRecipient('123', false)
  expect(api.setRecipientEnabled).toHaveBeenCalledWith('123', false)
  expect(ok().recipients).toEqual([R('123', false)])
})

it('toggle failure keeps the old value with a message', async () => {
  await s().load()
  api.setRecipientEnabled.mockRejectedValue(new ApiUnavailable('x'))
  await s().toggleRecipient('123', false)
  expect(ok().recipients).toEqual([R('123')])
  expect(s().feedback.recipients['123']).toEqual({ kind: 'error', text: 'Backend недоступний' })
  expect(s().pending.recipients).toEqual({})
})

it('remove: deleted, or already gone (404) — either way the row disappears', async () => {
  await s().load()
  api.deleteRecipient.mockRejectedValue(new ApiRequestError(404, 'recipient not found'))
  api.listRecipients.mockResolvedValue([])
  await s().removeRecipient('123')
  expect(ok().recipients).toEqual([])
  expect(s().feedback.recipients['123']).toBeUndefined()
})

// test message

it('test: ok, Telegram refusal (warning), request failure (error)', async () => {
  await s().load()
  let release!: () => void
  api.testRecipient.mockReturnValue(new Promise((r) => { release = () => r({ ok: true }) }))
  const p = s().testRecipient('123')
  expect(s().pending.recipients['123']).toBe('test')
  release()
  await p
  expect(s().feedback.recipients['123']).toEqual({ kind: 'ok', text: 'Тестове повідомлення надіслано' })

  const refusal = "HTTP 403: Forbidden: bot can't initiate conversation with a user"
  api.testRecipient.mockResolvedValue({ ok: false, error: refusal })
  await s().testRecipient('123')
  expect(s().feedback.recipients['123']).toEqual({ kind: 'warning', text: refusal })
  expect(s().feedback.schedule).toBeUndefined()

  api.testRecipient.mockRejectedValue(new ApiRequestError(409, 'TELEGRAM_BOT_TOKEN не задано'))
  await s().testRecipient('123')
  expect(s().feedback.recipients['123']).toEqual({ kind: 'error', text: 'TELEGRAM_BOT_TOKEN не задано' })
})

// candidates

const OLENA = { chat_id: '987654321', type: 'private', title: 'Олена', username: 'olena',
  last_seen_at: '2026-09-29T08:51:30Z', added: false }

it('load does not ask Telegram for candidates', async () => {
  await s().load()
  expect(api.listCandidates).not.toHaveBeenCalled()
  expect(s().candidates).toEqual({ state: 'idle' })
})

it('findCandidates: loading, ok, and the Telegram error text from a 502', async () => {
  let release!: () => void
  api.listCandidates.mockReturnValue(new Promise((r) => { release = () => r([OLENA]) }))
  const p = s().findCandidates()
  expect(s().candidates).toEqual({ state: 'loading' })
  release()
  await p
  expect(s().candidates).toEqual({ state: 'ok', items: [OLENA] })

  api.listCandidates.mockRejectedValue(new ApiUnavailable("HTTP 409: Conflict: webhook is active"))
  await s().findCandidates()
  expect(s().candidates).toEqual({ state: 'error', message: 'HTTP 409: Conflict: webhook is active' })

  api.listCandidates.mockRejectedValue(new ApiUnavailable('HTTP 502'))
  await s().findCandidates()
  expect(s().candidates).toEqual({ state: 'error', message: 'Backend недоступний' })
})

it('addCandidate adds the recipient and refreshes the added flags from the server', async () => {
  await s().load()
  api.addRecipient.mockResolvedValue(R('987654321'))
  api.listRecipients.mockResolvedValue([R('123'), R('987654321')])
  api.listCandidates.mockResolvedValue([{ ...OLENA, added: true }])
  await s().addCandidate('987654321')
  expect(api.addRecipient).toHaveBeenCalledWith('987654321')
  expect(ok().recipients).toEqual([R('123'), R('987654321')])
  expect(s().candidates).toEqual({ state: 'ok', items: [{ ...OLENA, added: true }] })
})

it('addCandidate failure lands in the add feedback and skips the refresh', async () => {
  await s().load()
  api.addRecipient.mockRejectedValue(new ApiValidationError('некоректний chat_id'))
  await s().addCandidate('x')
  expect(s().feedback.adding).toEqual({ kind: 'error', text: 'некоректний chat_id' })
  expect(api.listCandidates).not.toHaveBeenCalled()
})
