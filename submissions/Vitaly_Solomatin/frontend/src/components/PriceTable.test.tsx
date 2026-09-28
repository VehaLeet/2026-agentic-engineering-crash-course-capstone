import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it } from 'vitest'
import { daily, hourly } from '../test/prices-fixtures.ts'
import { PriceTable } from './PriceTable.tsx'

const headers = () => screen.getAllByRole('columnheader').map((h) => h.textContent)
const bodyRows = () => within(screen.getAllByRole('rowgroup')[1]).getAllByRole('row')

it('hourly columns and 24 rows for one day', () => {
  render(<PriceTable data={hourly()} />)
  expect(headers().slice(0, 4)).toEqual(['Дата', 'Період', 'Час (Київ)', 'Ціна, грн/МВт·год'])
  expect(headers()).toHaveLength(8)
  expect(bodyRows()).toHaveLength(24)
  expect(bodyRows()[12]).toHaveTextContent('12:00')
})

it('daily columns, dash for missing weighted price', () => {
  render(<PriceTable data={daily()} />)
  expect(headers()).toContain('Зважена, грн/МВт·год')
  expect(headers()).toContain('Періодів')
  expect(bodyRows()[0].textContent?.replace(/\s/g, ' ')).toContain('6 560,60')
  expect(bodyRows()[1]).toHaveTextContent('—')
})

it('pages by 100: 8760 rows -> page 1 of 88', () => {
  render(<PriceTable data={hourly('2025-01-01', 8760)} />)
  expect(bodyRows()).toHaveLength(100)
  expect(screen.getByText('Сторінка 1 з 88')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Наступна ›' }))
  expect(screen.getByText('Сторінка 2 з 88')).toBeInTheDocument()
})

it('new data starts again from the first page', () => {
  const view = render(<PriceTable data={hourly('2025-01-01', 300)} />)
  fireEvent.click(screen.getByRole('button', { name: 'Наступна ›' }))
  expect(screen.getByText('Сторінка 2 з 3')).toBeInTheDocument()
  view.rerender(<PriceTable data={hourly('2025-02-01', 300)} />)
  expect(screen.getByText('Сторінка 1 з 3')).toBeInTheDocument()
})
