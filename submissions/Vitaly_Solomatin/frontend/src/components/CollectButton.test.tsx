import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { Run } from '../api/types.ts'
import { useCollect, type Collect } from '../state/collect.ts'
import { CollectButton } from './CollectButton.tsx'

const run = (status: Run['status'], extra: Partial<Run> = {}): Run => ({
  id: 5, started_at: '2026-09-28T10:00:00Z', finished_at: '2026-09-28T10:00:02Z',
  status, trigger: 'manual', changed_days: [], error_message: null, ...extra,
})
const start = vi.fn().mockResolvedValue(undefined)
const show = (collect: Collect) => {
  useCollect.setState({ collect, start })
  render(<CollectButton />)
}
beforeEach(() => start.mockClear())

it('idle: clickable "Оновити зараз"', () => {
  show({ phase: 'idle' })
  fireEvent.click(screen.getByRole('button', { name: 'Оновити зараз' }))
  expect(start).toHaveBeenCalledTimes(1)
})

it('running: disabled and says the collection is in progress', () => {
  show({ phase: 'running', runId: 5 })
  const b = screen.getByRole('button', { name: 'Збір виконується…' })
  expect(b).toBeDisabled()
  fireEvent.click(b)
  expect(start).not.toHaveBeenCalled()
})

it.each([
  [run('success', { changed_days: ['2026-09-29'] }), 'Дані оновлено: 29.09.2026'],
  [run('no_changes'), 'Нових даних немає'],
  [run('no_data'), 'ОРЕЕ ще не опублікував дані'],
  [run('skipped_locked'), 'Збір уже виконується'],
])('non-error result %# is a status, not an alert', (r, text) => {
  show({ phase: 'done', run: r })
  expect(screen.getByRole('status')).toHaveTextContent(text)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('error result is an alert with the logged message', () => {
  show({ phase: 'done', run: run('error', { error_message: 'FetchError: таймаут' }) })
  expect(screen.getByRole('alert')).toHaveTextContent('Помилка збору: FetchError: таймаут')
})

it('timeout is a status, failed is an alert', () => {
  show({ phase: 'timeout', runId: 5 })
  expect(screen.getByRole('status')).toHaveTextContent('довше, ніж очікувалось')
  expect(screen.getByRole('button', { name: 'Оновити зараз' })).toBeEnabled()
})

it('failed start is an alert and the button is available again', () => {
  show({ phase: 'failed', message: 'Backend недоступний' })
  expect(screen.getByRole('alert')).toHaveTextContent('Backend недоступний')
  expect(screen.getByRole('button', { name: 'Оновити зараз' })).toBeEnabled()
})
