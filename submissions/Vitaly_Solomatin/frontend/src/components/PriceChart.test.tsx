import { render } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { daily, hourly } from '../test/prices-fixtures.ts'

const instance = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }
vi.mock('./chart/echarts.ts', () => ({ echarts: { init: vi.fn(() => instance) } }))
const { PriceChart } = await import('./PriceChart.tsx')
const { echarts } = await import('./chart/echarts.ts')

beforeEach(() => vi.clearAllMocks())

it('initialises once, sets option on data change, disposes on unmount', () => {
  const view = render(<PriceChart data={hourly()} />)
  expect(echarts.init).toHaveBeenCalledTimes(1)
  expect(instance.setOption).toHaveBeenCalledTimes(1)
  view.rerender(<PriceChart data={daily()} />)
  expect(instance.setOption).toHaveBeenCalledTimes(2)
  expect(echarts.init).toHaveBeenCalledTimes(1)
  view.unmount()
  expect(instance.dispose).toHaveBeenCalledTimes(1)
})
