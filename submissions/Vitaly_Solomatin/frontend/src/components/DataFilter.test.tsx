import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { usePrices } from '../state/prices.ts'
import { DataFilter } from './DataFilter.tsx'

const load = vi.fn().mockResolvedValue(undefined)
beforeEach(() => {
  load.mockClear()
  usePrices.setState({ range: { from: '2026-09-23', to: '2026-09-29' }, resolution: 'hour', load })
})

it('hourly is enabled for a short range', () => {
  render(<DataFilter />)
  expect(screen.getByRole('button', { name: 'Погодинно' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Погодинно' })).toHaveAttribute('aria-pressed', 'true')
})

it('"Уся історія" switches to daily, disables hourly and explains why', () => {
  render(<DataFilter />)
  fireEvent.click(screen.getByRole('button', { name: 'Уся історія' }))
  expect(usePrices.getState().range.from).toBe('2019-07-01')
  expect(screen.getByRole('button', { name: 'Погодинно' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Подобово' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText(/не більше 366 діб/)).toBeInTheDocument()
  expect(load).toHaveBeenCalled()
})

it('editing a date updates the range', () => {
  render(<DataFilter />)
  fireEvent.change(screen.getByLabelText('Від'), { target: { value: '2026-09-01' } })
  expect(usePrices.getState().range).toEqual({ from: '2026-09-01', to: '2026-09-29' })
})
