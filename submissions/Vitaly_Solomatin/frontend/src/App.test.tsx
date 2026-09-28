import { render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useConnection } from './state/connection.ts'
import { usePrices } from './state/prices.ts'

vi.mock('./components/PriceChart.tsx', () => ({ PriceChart: () => null }))
const { default: App } = await import('./App.tsx')

it('checks the connection and loads the default range once on mount', () => {
  const check = vi.fn().mockResolvedValue(undefined)
  const load = vi.fn().mockResolvedValue(undefined)
  useConnection.setState({ connection: { state: 'loading' }, check })
  usePrices.setState({ prices: { state: 'loading' }, load })
  render(<App />)
  expect(check).toHaveBeenCalledTimes(1)
  expect(load).toHaveBeenCalledTimes(1)
  expect(usePrices.getState().resolution).toBe('hour')
})
