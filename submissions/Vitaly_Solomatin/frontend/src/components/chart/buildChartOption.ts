import type { Prices } from '../../api/prices.ts'
import { formatPrice, formatVolume } from '../../lib/format.ts'
import { dailyLabel, hourlyLabels } from '../../lib/kyiv.ts'
import { palette } from '../../theme.ts'
import type { ChartOption } from './echarts.ts'

export const LARGE_SERIES = 1000

const PRICE_AXIS = 'грн/МВт·год'
const VOLUME_AXIS = 'МВт·год'

/**
 * Опція графіка — чиста функція від даних, тестується без canvas.
 * Вісь X категорійна з підписами за Києвом: вісь `time` ECharts підписує мітки за поясом браузера.
 */
export function buildChartOption(data: Prices): ChartOption {
  const n = data.delivery_date.length
  const large = n > LARGE_SERIES
  const labels = data.resolution === 'hour'
    ? hourlyLabels(data.delivery_date, data.period)
    : data.delivery_date.map(dailyLabel)
  // Проріджування лише рендеру; таблиця й підказка показують точні значення.
  const lineExtras = large ? { sampling: 'lttb' as const, showSymbol: false } : { showSymbol: n <= 48 }

  const series = data.resolution === 'hour'
    ? [
        { name: 'Ціна', type: 'line', yAxisIndex: 0, data: data.price, color: palette.navy900, lineStyle: { width: 2 }, ...lineExtras },
        { name: 'Обсяг продажу', type: 'bar', yAxisIndex: 1, data: data.volume_sell, color: palette.gray300, large },
      ]
    : [
        { name: 'Зважена ціна', type: 'line', yAxisIndex: 0, data: data.price_weighted, color: palette.navy900, lineStyle: { width: 2 }, connectNulls: false, ...lineExtras },
        { name: 'Мінімум', type: 'line', yAxisIndex: 0, data: data.price_min, color: palette.navy400, lineStyle: { width: 1, type: 'dashed' }, ...lineExtras },
        { name: 'Максимум', type: 'line', yAxisIndex: 0, data: data.price_max, color: palette.navy700, lineStyle: { width: 1, type: 'dashed' }, ...lineExtras },
        { name: 'Обсяг продажу', type: 'bar', yAxisIndex: 1, data: data.volume_sell, color: palette.gray300, large },
      ]

  const axisText = { color: palette.gray600 }
  return {
    animation: !large, // анімація не з'їдає бюджет «< 1 с» на довгих рядах
    color: series.map((s) => s.color),
    textStyle: { fontFamily: 'system-ui, sans-serif', color: palette.gray900 },
    grid: { left: 64, right: 72, top: 40, bottom: 48 },
    legend: { top: 0, textStyle: axisText },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => (typeof v === 'number' ? formatPrice(v) : '—'),
    },
    xAxis: { type: 'category', data: labels, axisLabel: axisText, axisLine: { lineStyle: { color: palette.gray300 } } },
    yAxis: [
      { type: 'value', name: PRICE_AXIS, nameTextStyle: axisText, axisLabel: { ...axisText, formatter: (v: number) => formatPrice(v).replace(/,00$/, '') }, splitLine: { lineStyle: { color: palette.gray300 } } },
      { type: 'value', name: VOLUME_AXIS, nameTextStyle: axisText, axisLabel: { ...axisText, formatter: (v: number) => formatVolume(v).replace(/,0$/, '') }, splitLine: { show: false } },
    ],
    series,
  }
}
