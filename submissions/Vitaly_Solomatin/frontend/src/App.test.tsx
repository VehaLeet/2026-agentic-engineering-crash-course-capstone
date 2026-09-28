import { render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App.tsx'
import { useConnection } from './state/connection.ts'

it('checks the connection once on mount', () => {
  const check = vi.fn().mockResolvedValue(undefined)
  useConnection.setState({ connection: { state: 'loading' }, check })
  render(<App />)
  expect(check).toHaveBeenCalledTimes(1)
})
