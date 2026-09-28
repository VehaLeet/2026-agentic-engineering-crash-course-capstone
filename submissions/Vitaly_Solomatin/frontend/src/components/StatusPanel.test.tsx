import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'
import { useCollect } from '../state/collect.ts'
import { useConnection } from '../state/connection.ts'
import { StatusPanel } from './StatusPanel.tsx'

const ok = (lastRunStatus: 'success' | null, lastCheck: string | null = '2026-09-28T09:00:00Z') => ({
  connection: { state: 'ok' as const, lastCheck, lastUpdate: null, lastRunStatus, recentErrors: [] },
})
beforeEach(() => useCollect.setState({ collect: { phase: 'idle' } }))

it('an unfinished last run while idle is shown as "не завершено"', () => {
  useConnection.setState(ok(null))
  render(<StatusPanel />)
  expect(screen.getByText('Останній запуск не завершено')).toBeInTheDocument()
})

it('our own running collection is not shown as "не завершено"', () => {
  useConnection.setState(ok(null))
  useCollect.setState({ collect: { phase: 'running', runId: 5 } })
  render(<StatusPanel />)
  expect(screen.queryByText('Останній запуск не завершено')).not.toBeInTheDocument()
})

it('an empty log (no runs at all) is not "не завершено"', () => {
  useConnection.setState(ok(null, null))
  render(<StatusPanel />)
  expect(screen.queryByText('Останній запуск не завершено')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Оновити зараз' })).toBeInTheDocument()
})
