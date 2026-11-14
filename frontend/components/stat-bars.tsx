import Link from "next/link"

export const percent = (part: number, total: number) => (total ? Math.round((part / total) * 100) : 0)

export function Meter({ value, max, label, color }: { value: number; max: number; label: string; color?: string }) {
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className="h-1.5 overflow-hidden rounded-full bg-muted"
    >
      <div
        className="h-full rounded-full bg-chart-1"
        style={{ width: `${max ? (value / max) * 100 : 0}%`, background: color }}
      />
    </div>
  )
}

/** A share of a whole: "described/total unit", with the percentage in large type when `large`. */
export function Coverage({
  label,
  unit,
  done,
  total,
  doneLabel,
  large = false,
}: {
  label: string
  unit: string
  done: number
  total: number
  /** What `done` means, for screen readers: "đã mô tả", "đã phân miền". */
  doneLabel: string
  large?: boolean
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm">{label}</span>
        <span className="text-sm text-muted-foreground tabular-nums">
          <span className="text-foreground">{done}</span>/{total} {unit}
        </span>
      </div>
      {large && <span className="text-3xl font-semibold tracking-tight tabular-nums">{percent(done, total)}%</span>}
      <Meter value={done} max={total} label={`${label}: ${done}/${total} ${unit} ${doneLabel}`} />
    </div>
  )
}

export type RankItem = {
  id: string
  label: string
  title: string
  value: number
  href: string
  color?: string
}

/** Rows of a name, a bar against the largest value and the value itself; each row links somewhere. */
export function RankList({ items, unit }: { items: RankItem[]; unit: string }) {
  const max = Math.max(...items.map((item) => item.value), 1)

  return (
    <ol className="flex flex-col">
      {items.map((item) => (
        <li key={item.id}>
          <Link
            href={item.href}
            title={item.title}
            className="-mx-2 grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_4rem] items-center gap-3 rounded-md px-2 py-1.5 text-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            <span className="flex min-w-0 items-center gap-2">
              {item.color ? <span className="size-2.5 shrink-0 rounded-full" style={{ background: item.color }} /> : null}
              <span className="truncate">{item.label}</span>
            </span>
            <Meter value={item.value} max={max} label={`${item.label}: ${item.value} ${unit}`} color={item.color} />
            <span className="text-right text-muted-foreground tabular-nums">
              <span className="font-medium text-foreground">{item.value}</span> {unit}
            </span>
          </Link>
        </li>
      ))}
    </ol>
  )
}

export type Share = { key: string; label: string; value: number; color: string }

/** A whole split into parts: one bar with a 2px gap between parts, and a legend that carries every count. */
export function ShareBar({ parts, unit, label }: { parts: Share[]; unit: string; label: string }) {
  const total = parts.reduce((sum, part) => sum + part.value, 0)

  return (
    <div className="flex flex-col gap-2.5">
      <div
        role="img"
        aria-label={`${label}: ${parts.map((part) => `${part.label} ${part.value}`).join(", ")} ${unit}`}
        className="flex h-2.5 gap-0.5 overflow-hidden rounded-sm bg-muted"
      >
        {parts
          .filter((part) => part.value > 0)
          .map((part) => (
            <div
              key={part.key}
              title={`${part.label}: ${part.value} ${unit} (${percent(part.value, total)}%)`}
              className="h-full min-w-1 transition-[flex-grow]"
              style={{ flexGrow: part.value, background: part.color }}
            />
          ))}
      </div>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-x-4 gap-y-1 text-sm">
        {parts.map((part) => (
          <li key={part.key} className="flex min-w-0 items-center gap-2">
            <span className="size-2.5 shrink-0 rounded-full" style={{ background: part.color }} />
            <span className="truncate text-muted-foreground">{part.label}</span>
            <span className="ml-auto font-medium tabular-nums">{part.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
