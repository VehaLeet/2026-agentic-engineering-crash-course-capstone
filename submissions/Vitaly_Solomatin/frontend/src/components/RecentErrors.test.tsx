import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import type { Run } from '../api/types.ts'
import { RecentErrors } from './RecentErrors.tsx'

const err = (id: number, started_at: string, msg: string): Run => ({
  id, started_at, finished_at: started_at, status: 'error', trigger: 'manual', changed_days: [], error_message: msg,
})

it('lists errors newest first with Kyiv time', () => {
  render(<RecentErrors errors={[err(9, '2026-09-28T09:00:00Z', 'друга'), err(3, '2026-09-27T09:00:00Z', 'перша')]} />)
  const items = screen.getAllByRole('listitem')
  expect(items[0]).toHaveTextContent('12:00')
  expect(items[0]).toHaveTextContent('друга')
  expect(items[1]).toHaveTextContent('перша')
})

it('says explicitly when there are no errors', () => {
  render(<RecentErrors errors={[]} />)
  expect(screen.getByText('Помилок збору немає')).toBeInTheDocument()
})
