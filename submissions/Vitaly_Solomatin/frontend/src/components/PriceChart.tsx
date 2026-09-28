import { useMemo, useRef } from 'react'
import type { Prices } from '../api/prices.ts'
import { buildChartOption } from './chart/buildChartOption.ts'
import { useEChart } from './chart/useEChart.ts'

export function PriceChart({ data }: { data: Prices }) {
  const ref = useRef<HTMLDivElement>(null)
  const option = useMemo(() => buildChartOption(data), [data])
  useEChart(ref, option)
  return <div ref={ref} className="chart" role="img" aria-label="Графік цін і обсягів РДН" />
}
