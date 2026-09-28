import { useEffect, useRef, type RefObject } from 'react'
import { lastLoadStartedAt } from '../../state/prices.ts'
import { echarts, type ChartOption } from './echarts.ts'

/** Єдине місце, що торкається canvas: init / setOption / resize / dispose. */
export function useEChart(ref: RefObject<HTMLDivElement | null>, option: ChartOption | null): void {
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const instance = echarts.init(ref.current)
    chart.current = instance
    const onResize = () => instance.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      instance.dispose()
      chart.current = null
    }
  }, [ref])

  useEffect(() => {
    if (!chart.current || !option) return
    const t0 = performance.now()
    chart.current.setOption(option, { notMerge: true })
    if (import.meta.env.DEV) {
      const now = performance.now()
      const points = ((option.xAxis as { data?: unknown[] } | undefined)?.data ?? []).length
      console.info(`[chart] ${points} точок: від вибору до графіка ${Math.round(now - lastLoadStartedAt())} мс, з них рендер ${Math.round(now - t0)} мс`)
    }
  }, [option])
}
