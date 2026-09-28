// Модульний імпорт: лише потрібні частини ECharts, а не весь пакет.
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

export { echarts }
export type { EChartsCoreOption as ChartOption } from 'echarts/core'
