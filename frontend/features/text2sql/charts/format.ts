// Vietnamese number and date formatting, the same rules as backend/modules/text2sql/services/display_format.py
// (vi_number, number_display, date_display, bucket_display, period_label). Both sides run
// tests/fixtures/format_cases.json. Pure functions: also run by `node --test`.

import type { ChartField, DateFormat, NumberFormat, TimeUnit } from "./spec.ts"

const WEEKDAYS = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]
const NON_FINITE = new Set(["nan", "-nan", "infinity", "-infinity", "+infinity", "inf", "-inf", "+inf"])
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export const EMPTY_LABEL = "(Trống)"
export const MISSING = "—"

export const isFiniteNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value)

export const isNonFinite = (value: unknown) =>
  (typeof value === "number" && !Number.isFinite(value)) ||
  (typeof value === "string" && NON_FINITE.has(value.trim().toLowerCase()))

// A decimal as digits × 10^exp, read from the shortest round-trip text of the number like Python's Decimal(repr(x)).
type Decimal = { negative: boolean; digits: bigint; exp: number }

function toDecimal(value: number): Decimal {
  const text = String(Math.abs(value)).toLowerCase()
  const [mantissa, power = "0"] = text.split("e")
  const [whole, fraction = ""] = mantissa.split(".")
  const negative = value < 0 || Object.is(value, -0)
  return { negative, digits: BigInt(whole + fraction || "0"), exp: Number(power) - fraction.length }
}

// Position of the most significant digit, like Decimal.adjusted().
const adjusted = (value: Decimal) => (value.digits === BigInt(0) ? 0 : value.digits.toString().length - 1 + value.exp)

function quantize(value: Decimal, places: number): Decimal {
  const shift = -places - value.exp
  if (shift <= 0) return { ...value, digits: value.digits * BigInt(10) ** BigInt(-shift), exp: -places }
  const divisor = BigInt(10) ** BigInt(shift)
  let digits = value.digits / divisor
  // ROUND_HALF_UP on the absolute value: a half rounds away from zero.
  if ((value.digits % divisor) * BigInt(2) >= divisor) digits += BigInt(1)
  return { ...value, digits, exp: -places }
}

function decimalText(value: Decimal, decimals: number | null | undefined, grouped: boolean): string {
  const places =
    decimals ?? (value.digits !== BigInt(0) && adjusted(value) < 0 ? Math.max(0, 2 - adjusted(value)) : 2)
  const rounded = quantize(value, places)
  const text = rounded.digits.toString().padStart(places + 1, "0")
  let whole = places ? text.slice(0, -places) : text
  const fraction = (places ? text.slice(-places) : "").replace(/0+$/, "")
  if (grouped) whole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".")
  const zero = rounded.digits === BigInt(0)
  const sign = rounded.negative && !zero ? "-" : ""
  return fraction ? `${sign}${whole},${fraction}` : `${sign}${whole}`
}

export function viNumber(value: number, decimals?: number | null, grouped = true): string {
  return decimalText(toDecimal(value), decimals, grouped)
}

const percentOf = (value: number, decimals?: number | null) => {
  const decimal = toDecimal(value)
  return `${decimalText({ ...decimal, exp: decimal.exp + 2 }, decimals, true)}%`
}

// The number alone, without unit; null for anything that is not a finite number.
export function numberDisplay(value: unknown, field: Pick<ChartField, "format_hint" | "percent" | "decimals">) {
  if (!isFiniteNumber(value)) return null
  if (field.format_hint === "plain") return viNumber(value, 0, false)
  if (field.percent) return percentOf(value, field.decimals)
  if (field.decimals !== null && field.decimals !== undefined) return viNumber(value, field.decimals)
  if (Number.isInteger(value)) return viNumber(value, 0)
  return viNumber(value, null)
}

const withUnit = (text: string, unit: string | null | undefined) => (unit ? `${text} ${unit}` : text)

const COMPACT: [number, string][] = [
  [1e12, "Nghìn tỷ"],
  [1e9, "Tỷ"],
  [1e6, "Tr"],
  [1e3, "N"],
]

// Short axis numbers: 1,2 N; 3 Tr; 2,5 Tỷ (not for sentences).
export function compactNumber(value: number): string {
  const size = Math.abs(value)
  for (const [step, suffix] of COMPACT) {
    if (size >= step) return `${viNumber(value / step, size / step >= 100 ? 0 : 1)} ${suffix}`
  }
  return viNumber(value, Number.isInteger(value) ? 0 : size < 1 ? null : 1)
}

// A measure value with its unit, using the spec's number format over the field's own.
export function formatMeasure(value: unknown, field: ChartField | undefined, format?: NumberFormat | null): string {
  if (!isFiniteNumber(value)) return MISSING
  const base = field ?? { name: "", label: "", type: "number" as const }
  if (!format) {
    const text = numberDisplay(value, base) ?? MISSING
    return base.percent ? text : withUnit(text, base.unit)
  }
  const decimals = format.decimals ?? base.decimals
  if (format.style === "percent") {
    const ratio = format.percent_input === "percent" ? value / 100 : value
    return percentOf(ratio, decimals)
  }
  if (format.style === "compact") return withUnit(compactNumber(value), format.unit ?? base.unit)
  const text = numberDisplay(value, { ...base, decimals })
  return base.percent && !format.unit ? (text ?? MISSING) : withUnit(text ?? MISSING, format.unit ?? base.unit)
}

// Axis ticks: compact numbers, percent kept as percent.
export function formatAxis(value: unknown, field: ChartField | undefined, format?: NumberFormat | null): string {
  if (!isFiniteNumber(value)) return ""
  if (format?.style === "percent" || (!format && field?.percent)) {
    const ratio = format?.percent_input === "percent" ? value / 100 : value
    return percentOf(ratio, Math.abs(ratio) < 0.1 ? 1 : 0)
  }
  if (field?.format_hint === "plain") return viNumber(value, 0, false)
  return compactNumber(value)
}

// Dates are calendar days: read the digits, never through the browser's time zone.
type Day = { year: number; month: number; day: number }

export function parseDay(value: unknown): Day | null {
  if (typeof value !== "string" || !ISO_DATE.test(value.slice(0, 10))) return null
  const [year, month, day] = value.slice(0, 10).split("-").map(Number)
  return { year, month, day }
}

const dayNumber = (day: Day) => Date.UTC(day.year, day.month - 1, day.day) / 86400000
const fromNumber = (count: number): Day => {
  const date = new Date(count * 86400000)
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() }
}
const addDays = (day: Day, count: number) => fromNumber(dayNumber(day) + count)
// Monday is 0, like Python's date.weekday().
const weekday = (day: Day) => (new Date(dayNumber(day) * 86400000).getUTCDay() + 6) % 7

export const isoDay = (day: Day) =>
  `${day.year}-${String(day.month).padStart(2, "0")}-${String(day.day).padStart(2, "0")}`

export function todayIso(now = new Date()): string {
  return isoDay({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() })
}

const yearSuffix = (day: Day, today: Day) => (day.year !== today.year ? `/${day.year}` : "")

export function dateDisplay(value: unknown, today: string, withWeekday = true): string | null {
  const day = parseDay(value)
  const now = parseDay(today)
  if (!day || !now) return null
  const text = `${day.day}/${day.month}${yearSuffix(day, now)}`
  return withWeekday ? `${WEEKDAYS[weekday(day)]}, ${text}` : text
}

export function datetimeDisplay(value: unknown, today: string): string | null {
  if (typeof value !== "string") return null
  const found = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/.exec(value)
  if (!found) return null
  return `${found[2]}:${found[3]} ${dateDisplay(found[1], today)}`
}

function weekLabel(start: Day, today: Day): string {
  const end = addDays(start, 6)
  if (start.month === end.month && start.year === end.year) {
    return `tuần ${start.day}–${end.day}/${end.month}${yearSuffix(end, today)}`
  }
  const head = `${start.day}/${start.month}${start.year !== end.year ? yearSuffix(start, today) : ""}`
  return `tuần ${head}–${end.day}/${end.month}${yearSuffix(end, today)}`
}

// Bucket keys of charts/data.ts ("2026-11", "2026-Q4", "2026") read as their first day.
function bucketDay(value: unknown): Day | null {
  if (typeof value !== "string") return null
  const quarter = /^(\d{4})-Q([1-4])$/.exec(value)
  if (quarter) return { year: Number(quarter[1]), month: (Number(quarter[2]) - 1) * 3 + 1, day: 1 }
  if (/^\d{4}-\d{2}$/.test(value)) return parseDay(`${value}-01`)
  if (/^\d{4}$/.test(value)) return parseDay(`${value}-01-01`)
  return parseDay(value)
}

export function bucketDisplay(value: unknown, unit: TimeUnit, today: string, withWeekday = true): string | null {
  const day = bucketDay(value)
  const now = parseDay(today)
  if (!day || !now) return null
  if (unit === "day") return dateDisplay(isoDay(day), today, withWeekday)
  if (unit === "week") return weekLabel(addDays(day, -weekday(day)), now)
  if (unit === "month") return `tháng ${day.month}${yearSuffix(day, now)}`
  if (unit === "quarter") return `quý ${Math.floor((day.month - 1) / 3) + 1}${yearSuffix(day, now)}`
  return String(day.year)
}

// A period [start, before) as a short label: "19/11", "13–19/11", "tháng 11", "28/10–3/11/2025".
export function periodLabel(start: string, before: string, today: string): string {
  const first = parseDay(start)
  const next = parseDay(before)
  const now = parseDay(today)
  if (!first || !next || !now) return start
  const end = addDays(next, -1)
  if (dayNumber(end) <= dayNumber(first)) return dateDisplay(start, today) ?? start
  const nextMonth =
    first.month === 12 ? { year: first.year + 1, month: 1, day: 1 } : { ...first, month: first.month + 1, day: 1 }
  if (first.day === 1 && dayNumber(next) === dayNumber(nextMonth)) {
    return `tháng ${first.month}${yearSuffix(first, now)}`
  }
  const show = first.year !== now.year || end.year !== now.year
  const tail = show ? `/${end.year}` : ""
  if (first.month === end.month && first.year === end.year) return `${first.day}–${end.day}/${end.month}${tail}`
  const headYear = show && first.year !== end.year ? `/${first.year}` : ""
  return `${first.day}/${first.month}${headYear}–${end.day}/${end.month}${tail}`
}

export const nextDay = (value: string) => {
  const day = parseDay(value)
  return day ? isoDay(addDays(day, 1)) : value
}

// One table cell as text; null and non-finite values show as a dash.
export function cellText(value: unknown, field: ChartField | undefined, today: string): string {
  if (value === null || value === undefined) return MISSING
  if (!field) return String(value)
  if (field.type === "number") {
    if (isNonFinite(value)) return MISSING
    return isFiniteNumber(value) ? (numberDisplay(value, field) ?? MISSING) : String(value)
  }
  if (typeof value === "boolean") return value ? "Đúng" : "Sai"
  if (field.time_unit && (field.type === "date" || field.type === "datetime")) {
    return bucketDisplay(value, field.time_unit, today) ?? String(value)
  }
  if (field.type === "date") return dateDisplay(value, today) ?? String(value)
  if (field.type === "datetime") return datetimeDisplay(value, today) ?? String(value)
  return String(value)
}

// A dimension key from charts/data.ts as an axis or legend label.
export function keyText(
  key: string,
  field: ChartField | undefined,
  today: string,
  unit?: TimeUnit | null,
  style?: DateFormat["style"],
  long = false,
): string {
  if (!field) return key
  if (key === EMPTY_LABEL) return key
  if (field.type === "date" || field.type === "datetime") {
    const bucket = unit ?? field.time_unit
    if (style === "datetime" && field.type === "datetime") return datetimeDisplay(key, today) ?? key
    const chosen: TimeUnit | null =
      style && !["auto", "day_weekday", "datetime"].includes(style) ? (style as TimeUnit) : (bucket ?? null)
    if (chosen && chosen !== "day") return bucketDisplay(key, chosen, today) ?? key
    // An hourly series keeps its hours: the axis shows "06:00" and the date only at midnight.
    const time = field.type === "datetime" && !chosen ? /[T ](\d{2}:\d{2})/.exec(key)?.[1] : undefined
    if (time && time !== "00:00") return long ? (datetimeDisplay(key, today) ?? key) : time
    return dateDisplay(key, today, long || style === "day_weekday") ?? key
  }
  if (field.type === "boolean") return key === "true" ? "Đúng" : key === "false" ? "Sai" : key
  if (field.type === "number") {
    const value = Number(key)
    return Number.isFinite(value) ? (numberDisplay(value, field) ?? key) : key
  }
  return key
}

// Column header: label plus unit, e.g. "Tổng lượng mưa (mm)".
export function fieldTitle(field: ChartField): string {
  const unit = field.percent ? null : field.unit
  return unit && !field.label.includes(`(${unit})`) ? `${field.label} (${unit})` : field.label
}
