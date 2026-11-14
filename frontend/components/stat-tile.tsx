import { NumberRoll } from "@/components/number-roll"

export function StatTile({ label, value, total }: { label: string; value: number; total?: number }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border px-4 py-3">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-2xl font-semibold tracking-tight tabular-nums">
        <NumberRoll value={value} />
        {total !== undefined ? <span className="text-base font-normal text-muted-foreground">/{total}</span> : null}
      </span>
    </div>
  )
}
