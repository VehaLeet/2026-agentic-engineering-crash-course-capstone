import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import type { Connection } from '../state/connection.ts'
import { ConnectionPanel } from './ConnectionPanel.tsx'

it('loading', () => {
  render(<ConnectionPanel connection={{ state: 'loading' }} />)
  expect(screen.getByText(/Перевіряю/)).toBeInTheDocument()
})

it('ok shows Kyiv times', () => {
  render(<ConnectionPanel connection={{ state: 'ok', lastCheck: '2026-09-28T09:00:00Z', lastUpdate: '2026-09-28T09:00:00Z' }} />)
  expect(screen.getByText(/в порядку/)).toBeInTheDocument()
  expect(screen.getAllByText(/12:00/)).toHaveLength(2)
})

it('ok with an empty log shows "ще не було"', () => {
  render(<ConnectionPanel connection={{ state: 'ok', lastCheck: null, lastUpdate: null }} />)
  expect(screen.getAllByText('ще не було')).toHaveLength(2)
})

it('unavailable', () => {
  render(<ConnectionPanel connection={{ state: 'unavailable' }} />)
  expect(screen.getByText('Backend недоступний')).toBeInTheDocument()
  expect(screen.queryByText(/автентифікація/)).not.toBeInTheDocument()
})

it('contract error is shown, not empty values', () => {
  render(<ConnectionPanel connection={{ state: 'error', message: 'неочікувана відповідь /status' }} />)
  expect(screen.getByRole('alert')).toHaveTextContent('неочікувана відповідь /status')
})

it.each<Connection>([
  { state: 'loading' },
  { state: 'ok', lastCheck: null, lastUpdate: null },
  { state: 'unavailable' },
  { state: 'error', message: 'x' },
])('no login link or auth wording in state $state', (connection) => {
  const { container } = render(<ConnectionPanel connection={connection} />)
  expect(screen.queryByRole('link', { name: 'Увійти' })).not.toBeInTheDocument()
  expect(container.textContent).not.toMatch(/автентифіка/i)
})
