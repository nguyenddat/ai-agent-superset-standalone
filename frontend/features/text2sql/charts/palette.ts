import type { ColorScheme, PaletteToken } from "./spec"

// Spec colour tokens are CSS variables from app/globals.css, so light and dark each get their own validated steps.
export const tokenColor = (token: PaletteToken | null | undefined) =>
  token === "muted" ? "var(--chart-muted)" : `var(--chart-${(token ?? "series-1").replace("series-", "")})`

const SEQUENTIAL = [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700]

// Magnitude: one hue from light to dark; the lightest step stays visible against the surface.
export function sequentialColor(ratio: number) {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(ratio) ? ratio : 0))
  const step = SEQUENTIAL[Math.round(2 + clamped * (SEQUENTIAL.length - 3))]
  return `var(--chart-seq-${step})`
}

// Polarity: two hues meeting at a grey midpoint.
export function divergingColor(value: number, midpoint: number, extent: number) {
  if (!extent || value === midpoint) return "var(--chart-div-mid)"
  const ratio = Math.min(1, Math.abs(value - midpoint) / extent)
  const pole = value > midpoint ? "var(--chart-div-pos)" : "var(--chart-div-neg)"
  return `color-mix(in oklab, ${pole} ${Math.round(25 + ratio * 75)}%, var(--chart-div-mid))`
}

export function scaleColor(
  scheme: ColorScheme | undefined,
  value: number | null,
  min: number,
  max: number,
  midpoint?: number | null,
) {
  if (value === null) return "var(--muted)"
  if (scheme === "diverging") {
    const middle = midpoint ?? 0
    return divergingColor(value, middle, Math.max(Math.abs(max - middle), Math.abs(min - middle)))
  }
  return sequentialColor(max === min ? 1 : (value - min) / (max - min))
}
