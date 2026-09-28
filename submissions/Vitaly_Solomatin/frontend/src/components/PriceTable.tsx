import { useState } from 'react'
import type { Prices } from '../api/prices.ts'
import { formatPrice, formatVolume } from '../lib/format.ts'
import { dailyLabel, kyivTime, periodStart } from '../lib/kyiv.ts'

export const PAGE_SIZE = 100

type Column = { title: string; cell: (i: number) => string }

function columns(data: Prices): Column[] {
  const vol = (xs: number[]) => (i: number) => formatVolume(xs[i])
  const common = [
    { title: 'Обсяг продажу, МВт·год', cell: vol(data.volume_sell) },
    { title: 'Обсяг купівлі, МВт·год', cell: vol(data.volume_buy) },
    { title: 'Заявлений продаж, МВт·год', cell: vol(data.declared_volume_sell) },
    { title: 'Заявлена купівля, МВт·год', cell: vol(data.declared_volume_buy) },
  ]
  if (data.resolution === 'hour') {
    return [
      { title: 'Дата', cell: (i) => dailyLabel(data.delivery_date[i]) },
      { title: 'Період', cell: (i) => String(data.period[i]) },
      { title: 'Час (Київ)', cell: (i) => kyivTime(periodStart(data.delivery_date[i], data.period[i])) },
      { title: 'Ціна, грн/МВт·год', cell: (i) => formatPrice(data.price[i]) },
      ...common,
    ]
  }
  return [
    { title: 'Дата', cell: (i) => dailyLabel(data.delivery_date[i]) },
    { title: 'Мін', cell: (i) => formatPrice(data.price_min[i]) },
    { title: 'Макс', cell: (i) => formatPrice(data.price_max[i]) },
    { title: 'BASE', cell: (i) => formatPrice(data.price_avg[i]) },
    { title: 'Зважена, грн/МВт·год', cell: (i) => formatPrice(data.price_weighted[i]) },
    ...common,
    { title: 'Періодів', cell: (i) => String(data.periods[i]) },
  ]
}

export function PriceTable({ data }: { data: Prices }) {
  // Сторінка прив'язана до конкретних даних: нові дані — автоматично перша сторінка, без ефекту.
  const [paging, setPaging] = useState({ data, page: 0 })
  const page = paging.data === data ? paging.page : 0
  const setPage = (next: number) => setPaging({ data, page: next })
  const cols = columns(data)
  const total = data.delivery_date.length
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = page * PAGE_SIZE
  const rows = Array.from({ length: Math.min(PAGE_SIZE, total - start) }, (_, k) => start + k)
  return (
    <div>
      <table>
        <thead>
          <tr>{cols.map((c) => <th key={c.title} scope="col">{c.title}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((i) => <tr key={i}>{cols.map((c) => <td key={c.title}>{c.cell(i)}</td>)}</tr>)}
        </tbody>
      </table>
      {pages > 1 && (
        <nav className="pager" aria-label="Сторінки таблиці">
          <button type="button" onClick={() => setPage(page - 1)} disabled={page === 0}>‹ Попередня</button>
          <span>Сторінка {page + 1} з {pages}</span>
          <button type="button" onClick={() => setPage(page + 1)} disabled={page >= pages - 1}>Наступна ›</button>
        </nav>
      )}
    </div>
  )
}
