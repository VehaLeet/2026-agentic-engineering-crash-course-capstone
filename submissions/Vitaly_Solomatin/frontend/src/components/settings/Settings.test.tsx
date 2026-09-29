import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { NotificationsSettings, Recipient, Schedule } from '../../api/types.ts'
import { formatKyiv } from '../../lib/time.ts'
import { useSettings, type Settings } from '../../state/settings.ts'
import { NotificationsToggle } from './NotificationsToggle.tsx'
import { RecipientsList } from './RecipientsList.tsx'
import { ScheduleForm } from './ScheduleForm.tsx'
import { SettingsView } from './SettingsView.tsx'

const SCHEDULE: Schedule = { enabled: true, interval_minutes: 60, next_run_at: '2026-09-29T09:00:00Z' }
const NOTIFICATIONS: NotificationsSettings = { enabled: true, token_configured: true }
const actions = {
  load: vi.fn(), saveSchedule: vi.fn(), setNotifications: vi.fn(), addRecipient: vi.fn(),
  toggleRecipient: vi.fn(), removeRecipient: vi.fn(), testRecipient: vi.fn(),
}

function state(extra: Partial<ReturnType<typeof useSettings.getState>> = {}) {
  useSettings.setState({ ...actions, pending: { recipients: {} }, feedback: { recipients: {} }, ...extra })
}

beforeEach(() => {
  Object.values(actions).forEach((f) => f.mockReset().mockResolvedValue(true))
  state()
})
afterEach(() => vi.restoreAllMocks())

// SettingsView

it('loads on mount and shows the loading state', () => {
  state({ settings: { state: 'loading' } })
  render(<SettingsView />)
  expect(actions.load).toHaveBeenCalledTimes(1)
  expect(screen.getByText('Завантаження налаштувань…')).toBeInTheDocument()
})

it('backend unavailable: message and retry, no forms', () => {
  state({ settings: { state: 'unavailable' } })
  render(<SettingsView />)
  expect(screen.getByRole('alert')).toHaveTextContent('Backend недоступний')
  expect(screen.queryByText('Розклад збору')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Повторити' }))
  expect(actions.load).toHaveBeenCalledTimes(2)
})

it('ok: all three sections with loaded values', () => {
  const settings: Settings = { state: 'ok', schedule: SCHEDULE, notifications: NOTIFICATIONS, recipients: [{ chat_id: '123', enabled: true }] }
  state({ settings })
  render(<SettingsView />)
  expect(screen.getByLabelText('Інтервал, хвилин')).toHaveValue(60)
  expect(screen.getByLabelText('Збирати дані автоматично')).toBeChecked()
  expect(screen.getByLabelText('Надсилати сповіщення в Telegram')).toBeChecked()
  expect(screen.getByText('123')).toBeInTheDocument()
})

// ScheduleForm

it('shows the next run in Kyiv time, or "не заплановано"', () => {
  const { unmount } = render(<ScheduleForm schedule={SCHEDULE} />)
  expect(screen.getByText(`Наступний запуск: ${formatKyiv(SCHEDULE.next_run_at!)}`)).toBeInTheDocument()
  unmount()
  render(<ScheduleForm schedule={{ enabled: false, interval_minutes: 60, next_run_at: null }} />)
  expect(screen.getByText('Наступний запуск: не заплановано')).toBeInTheDocument()
})

it('save is disabled until the form changes; submits the new value', () => {
  render(<ScheduleForm schedule={SCHEDULE} />)
  const save = screen.getByRole('button', { name: 'Зберегти' })
  expect(save).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Інтервал, хвилин'), { target: { value: '15' } })
  expect(save).toBeEnabled()
  fireEvent.click(save)
  expect(actions.saveSchedule).toHaveBeenCalledWith({ enabled: true, interval_minutes: 15 })
})

it.each(['4', '1441', '7.5', ''])('interval %j is flagged and blocks saving', (value) => {
  render(<ScheduleForm schedule={SCHEDULE} />)
  fireEvent.change(screen.getByLabelText('Інтервал, хвилин'), { target: { value } })
  expect(screen.getByText('Ціле число хвилин від 5 до 1440')).toBeInTheDocument()
  expect(screen.getByLabelText('Інтервал, хвилин')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByRole('button', { name: 'Зберегти' })).toBeDisabled()
})

it('while saving the button is disabled; after a refusal the typed value stays', () => {
  state({ pending: { schedule: true, recipients: {} } })
  const { rerender } = render(<ScheduleForm schedule={SCHEDULE} />)
  fireEvent.change(screen.getByLabelText('Інтервал, хвилин'), { target: { value: '15' } })
  expect(screen.getByRole('button', { name: 'Збереження…' })).toBeDisabled()
  state({ feedback: { schedule: { kind: 'error', text: 'interval out of range' }, recipients: {} } })
  rerender(<ScheduleForm schedule={SCHEDULE} />)
  expect(screen.getByRole('alert')).toHaveTextContent('interval out of range')
  expect(screen.getByLabelText('Інтервал, хвилин')).toHaveValue(15)
  expect(screen.getByRole('button', { name: 'Зберегти' })).toBeEnabled()
})

// NotificationsToggle

it('toggle calls the store; disabled while saving', () => {
  const { unmount } = render(<NotificationsToggle notifications={NOTIFICATIONS} />)
  fireEvent.click(screen.getByLabelText('Надсилати сповіщення в Telegram'))
  expect(actions.setNotifications).toHaveBeenCalledWith(false)
  unmount()
  state({ pending: { notifications: true, recipients: {} } })
  render(<NotificationsToggle notifications={NOTIFICATIONS} />)
  expect(screen.getByLabelText('Надсилати сповіщення в Telegram')).toBeDisabled()
})

it('failed save: value unchanged, error shown', () => {
  state({ feedback: { notifications: { kind: 'error', text: 'Backend недоступний' }, recipients: {} } })
  render(<NotificationsToggle notifications={NOTIFICATIONS} />)
  expect(screen.getByLabelText('Надсилати сповіщення в Telegram')).toBeChecked()
  expect(screen.getByRole('alert')).toHaveTextContent('Backend недоступний')
})

it('warns when the bot token is not configured', () => {
  render(<NotificationsToggle notifications={{ enabled: true, token_configured: false }} />)
  expect(screen.getByText(/TELEGRAM_BOT_TOKEN/)).toBeInTheDocument()
})

// RecipientsList

const list = (recipients: Recipient[], tokenConfigured = true) =>
  render(<RecipientsList recipients={recipients} tokenConfigured={tokenConfigured} />)

it('empty list explains /start and adding the bot to a channel', () => {
  list([])
  expect(screen.getByText(/написати боту \/start/)).toBeInTheDocument()
  expect(screen.getByText(/адміністратором/)).toBeInTheDocument()
})

it('add: disabled for blank input, clears after success, keeps text after refusal', async () => {
  list([])
  const add = screen.getByRole('button', { name: 'Додати' })
  const input = screen.getByLabelText('chat_id')
  expect(add).toBeDisabled()
  fireEvent.change(input, { target: { value: '   ' } })
  expect(add).toBeDisabled()
  fireEvent.change(input, { target: { value: '123456789' } })
  fireEvent.click(add)
  expect(actions.addRecipient).toHaveBeenCalledWith('123456789')
  await vi.waitFor(() => expect(input).toHaveValue(''))
  actions.addRecipient.mockResolvedValue(false)
  fireEvent.change(input, { target: { value: 'hello world' } })
  fireEvent.click(add)
  await Promise.resolve()
  expect(input).toHaveValue('hello world')
})

it('toggle and delete with confirmation', () => {
  list([{ chat_id: '123', enabled: true }])
  fireEvent.click(screen.getByLabelText('Надсилати отримувачу 123'))
  expect(actions.toggleRecipient).toHaveBeenCalledWith('123', false)
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  fireEvent.click(screen.getByRole('button', { name: 'Видалити' }))
  expect(actions.removeRecipient).not.toHaveBeenCalled()
  confirm.mockReturnValue(true)
  fireEvent.click(screen.getByRole('button', { name: 'Видалити' }))
  expect(actions.removeRecipient).toHaveBeenCalledWith('123')
})

it('test: sending state, result next to the right recipient', () => {
  state({
    pending: { recipients: { '111': 'test' } },
    feedback: { recipients: { '222': { kind: 'warning', text: "HTTP 403: bot can't initiate conversation" } } },
  })
  list([{ chat_id: '111', enabled: true }, { chat_id: '222', enabled: true }])
  expect(screen.getByRole('button', { name: 'Надсилаємо…' })).toBeDisabled()
  const rows = screen.getAllByRole('listitem')
  expect(rows[1]).toHaveTextContent("bot can't initiate conversation")
  expect(rows[0]).not.toHaveTextContent("bot can't initiate conversation")
  expect(screen.queryByRole('alert')).toBeNull() // відмова Telegram — не збій застосунку
  fireEvent.click(screen.getAllByRole('button', { name: 'Надіслати тест' })[0])
  expect(actions.testRecipient).toHaveBeenCalledWith('222')
})

it('without a token the test buttons are disabled with an explanation', () => {
  list([{ chat_id: '123', enabled: true }], false)
  expect(screen.getByRole('button', { name: 'Надіслати тест' })).toBeDisabled()
  expect(screen.getByText(/Тестове повідомлення недоступне: токен бота не задано/)).toBeInTheDocument()
})
