import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { Candidate } from '../../api/types.ts'
import { formatKyiv } from '../../lib/time.ts'
import { useSettings, type Candidates as CandidatesState } from '../../state/settings.ts'
import { Candidates } from './Candidates.tsx'

const findCandidates = vi.fn()
const addCandidate = vi.fn()
const OLENA: Candidate = { chat_id: '987654321', type: 'private', title: 'Олена', username: 'olena',
  last_seen_at: '2026-09-29T08:51:30Z', added: false }
const CHANNEL: Candidate = { chat_id: '-1001234567890', type: 'channel', title: 'Ціни РДН', username: null,
  last_seen_at: '2026-09-29T08:00:00Z', added: true }

function show(candidates: CandidatesState, tokenConfigured = true) {
  useSettings.setState({ candidates, findCandidates, addCandidate, pending: { recipients: {} } })
  render(<Candidates tokenConfigured={tokenConfigured} />)
}

beforeEach(() => {
  findCandidates.mockReset().mockResolvedValue(undefined)
  addCandidate.mockReset().mockResolvedValue(undefined)
})

it('asks the server only when the button is pressed', () => {
  show({ state: 'idle' })
  expect(findCandidates).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Знайти чати' }))
  expect(findCandidates).toHaveBeenCalledTimes(1)
})

it('disabled while searching', () => {
  show({ state: 'loading' })
  expect(screen.getByRole('button', { name: 'Шукаємо…' })).toBeDisabled()
})

it('disabled with an explanation without a bot token', () => {
  show({ state: 'idle' }, false)
  expect(screen.getByRole('button', { name: 'Знайти чати' })).toBeDisabled()
  expect(screen.getByText(/токен бота не задано/)).toBeInTheDocument()
})

it('lists name, username, type and Kyiv time; add only for new chats', () => {
  show({ state: 'ok', items: [OLENA, CHANNEL] })
  const [olena, channel] = screen.getAllByRole('listitem')
  expect(olena).toHaveTextContent('Олена')
  expect(olena).toHaveTextContent('@olena')
  expect(olena).toHaveTextContent('особистий чат')
  expect(olena).toHaveTextContent(formatKyiv(OLENA.last_seen_at))
  expect(channel).toHaveTextContent('Ціни РДН')
  expect(channel).toHaveTextContent('канал')
  expect(channel).toHaveTextContent('вже додано')
  expect(screen.getAllByRole('button', { name: 'Додати' })).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Додати' }))
  expect(addCandidate).toHaveBeenCalledWith('987654321')
})

it('explains the 24-hour window when nothing is found', () => {
  show({ state: 'ok', items: [] })
  expect(screen.getByText(/за останні 24 години/)).toBeInTheDocument()
})

it('shows the error text', () => {
  show({ state: 'error', message: "HTTP 409: Conflict: can't use getUpdates method while webhook is active" })
  expect(screen.getByRole('alert')).toHaveTextContent('webhook is active')
})
