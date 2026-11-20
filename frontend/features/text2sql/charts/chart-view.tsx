"use client"

import { Component, type ComponentType, type ReactNode } from "react"

import { typeLabel } from "./catalog"
import type { Row } from "./data"
import { BoxPlotRenderer, CartesianRenderer, HistogramRenderer, ScatterRenderer } from "./renderers/cartesian"
import type { RendererProps } from "./renderers/common"
import { BulletRenderer, KpiRenderer, SparklineTableRenderer, TableRenderer } from "./renderers/figures"
import { CalendarHeatmapRenderer, HeatmapRenderer } from "./renderers/grid"
import { SankeyRenderer, SunburstRenderer, TreemapRenderer } from "./renderers/hierarchy"
import { FunnelRenderer, PieRenderer, RadarRenderer, RadialBarRenderer } from "./renderers/polar"
import type { ChartField, ChartSpec, ChartType } from "./spec"

// Every chart type the frontend can draw; the type switcher only offers these.
export const RENDERERS: Partial<Record<ChartType, ComponentType<RendererProps>>> = {
  kpi: KpiRenderer,
  bullet: BulletRenderer,
  bar: CartesianRenderer,
  bar_horizontal: CartesianRenderer,
  bar_grouped: CartesianRenderer,
  lollipop: CartesianRenderer,
  dumbbell: CartesianRenderer,
  diverging_bar: CartesianRenderer,
  radial_bar: RadialBarRenderer,
  radar: RadarRenderer,
  bar_stacked: CartesianRenderer,
  bar_stacked_100: CartesianRenderer,
  pie: PieRenderer,
  donut: PieRenderer,
  treemap: TreemapRenderer,
  sunburst: SunburstRenderer,
  waterfall: CartesianRenderer,
  funnel: FunnelRenderer,
  line: CartesianRenderer,
  area: CartesianRenderer,
  area_stacked: CartesianRenderer,
  area_stacked_100: CartesianRenderer,
  combo: CartesianRenderer,
  sparkline_table: SparklineTableRenderer,
  calendar_heatmap: CalendarHeatmapRenderer,
  histogram: HistogramRenderer,
  box_plot: BoxPlotRenderer,
  heatmap: HeatmapRenderer,
  scatter: ScatterRenderer,
  bubble: ScatterRenderer,
  sankey: SankeyRenderer,
  table: TableRenderer,
}

export const canRender = (type: string) => type in RENDERERS

// A renderer that throws on unexpected data falls back to the table instead of breaking the conversation.
type GuardProps = { fallback: ReactNode; children: ReactNode; resetKey: string }

class Guard extends Component<GuardProps, { failed: string | null }> {
  state = { failed: null as string | null }

  static getDerivedStateFromError() {
    return { failed: "error" }
  }

  componentDidUpdate(previous: { resetKey: string }) {
    if (previous.resetKey !== this.props.resetKey && this.state.failed) this.setState({ failed: null })
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export function ChartView({
  spec,
  fields,
  rows,
  suggested,
  compact,
  showTitle = true,
}: {
  spec: ChartSpec
  fields: ChartField[]
  rows: Row[]
  suggested?: ChartSpec | null
  compact?: boolean
  showTitle?: boolean
}) {
  let shown = spec
  let note: string | null = null
  if (!canRender(spec.type)) {
    shown = suggested && canRender(suggested.type) ? suggested : { type: "table" }
    note = `Chưa hỗ trợ dạng «${typeLabel(spec.type)}»; đang hiện dạng «${typeLabel(shown.type)}».`
  }
  const Renderer = RENDERERS[shown.type] ?? TableRenderer
  const table = <TableRenderer spec={{ type: "table" }} fields={fields} rows={rows} />
  return (
    <figure className="flex min-w-0 flex-col gap-2" aria-label={shown.title ?? typeLabel(shown.type)}>
      {showTitle && (shown.title || shown.subtitle) && (
        <figcaption className="flex flex-col">
          {shown.title && <span className="text-sm font-medium">{shown.title}</span>}
          {shown.subtitle && <span className="text-xs text-muted-foreground">{shown.subtitle}</span>}
        </figcaption>
      )}
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
      <Guard
        resetKey={JSON.stringify(shown)}
        fallback={
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">Không vẽ được biểu đồ này; đang hiện dạng bảng.</p>
            {table}
          </div>
        }
      >
        <Renderer spec={shown} fields={fields} rows={rows} compact={compact} />
      </Guard>
    </figure>
  )
}
