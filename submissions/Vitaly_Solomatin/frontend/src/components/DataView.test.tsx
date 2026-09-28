import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { usePrices, type PricesState } from '../state/prices.ts'

vi.mock('./PriceChart.tsx', () => ({ PriceChart: () => <div>chart</div> }))
const { DataView } = await import('./DataView.tsx')

const load = vi.fn().mockResolvedValue(undefined)
const show = (prices: PricesState) => {
  usePrices.setState({ prices, load })
  render(<DataView />)
}
beforeEach(() => load.mockClear())

it('empty is a neutral message, not an alert', () => {
  show({ state: 'empty' })
  expect(screen.getByText('За цей період даних немає')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('unavailable is an alert, not "no data"', () => {
  show({ state: 'unavailable' })
  expect(screen.getByRole('alert')).toHaveTextContent('Backend недоступний')
  expect(screen.queryByText(/даних немає/)).not.toBeInTheDocument()
})

it('API validation message is shown', () => {
  show({ state: 'invalid', message: 'hourly range is limited to 366 days; use resolution=day' })
  expect(screen.getByRole('alert')).toHaveTextContent('resolution=day')
})

it('loads once on mount', () => {
  show({ state: 'loading' })
  expect(load).toHaveBeenCalledTimes(1)
})
