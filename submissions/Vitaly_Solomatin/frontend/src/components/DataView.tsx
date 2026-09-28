import { useEffect } from 'react'
import { usePrices } from '../state/prices.ts'
import { DataFilter } from './DataFilter.tsx'
import { PriceChart } from './PriceChart.tsx'
import { PriceTable } from './PriceTable.tsx'

function Body() {
  const prices = usePrices((s) => s.prices)
  switch (prices.state) {
    case 'loading':
      return <section className="card" aria-busy="true">Завантажую дані…</section>
    case 'empty':
      return <section className="card muted">За цей період даних немає</section>
    case 'unavailable':
      return <section className="card" role="alert">Backend недоступний</section>
    case 'invalid':
      return <section className="card" role="alert">{prices.message}</section>
    case 'error':
      return <section className="card" role="alert">Помилка даних: {prices.message}</section>
    case 'ok':
      return (
        <>
          <section className="card"><PriceChart data={prices.data} /></section>
          <section className="card"><PriceTable data={prices.data} /></section>
        </>
      )
  }
}

export function DataView() {
  const load = usePrices((s) => s.load)
  useEffect(() => {
    void load()
  }, [load])
  return (
    <>
      <DataFilter />
      <Body />
    </>
  )
}
