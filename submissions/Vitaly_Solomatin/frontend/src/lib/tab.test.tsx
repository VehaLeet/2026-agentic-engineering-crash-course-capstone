import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { Tabs } from '../components/Tabs.tsx'
import { tabFromHash, useTab } from './tab.ts'

function Harness() {
  const [tab, select] = useTab()
  return <><Tabs tab={tab} onSelect={select} /><p>active:{tab}</p></>
}

afterEach(() => { window.location.hash = '' })

it('maps the hash to a tab', () => {
  expect(tabFromHash('')).toBe('data')
  expect(tabFromHash('#settings')).toBe('settings')
  expect(tabFromHash('#other')).toBe('data')
})

it('defaults to data and switches to settings on click', () => {
  render(<Harness />)
  expect(screen.getByRole('tab', { name: 'Дані' })).toHaveAttribute('aria-selected', 'true')
  fireEvent.click(screen.getByRole('tab', { name: 'Налаштування' }))
  expect(window.location.hash).toBe('#settings')
  expect(screen.getByRole('tab', { name: 'Налаштування' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tablist')).toBeInTheDocument()
})

it('opens settings when the page loads with #settings', () => {
  window.location.hash = '#settings'
  render(<Harness />)
  expect(screen.getByText('active:settings')).toBeInTheDocument()
})

it('follows hashchange (browser back)', () => {
  window.location.hash = '#settings'
  render(<Harness />)
  act(() => {
    window.location.hash = ''
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  })
  expect(screen.getByText('active:data')).toBeInTheDocument()
})
