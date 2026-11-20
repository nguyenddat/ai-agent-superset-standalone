"use client"

import { ChevronDownIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { FAMILIES, TYPE_FAMILIES, TYPE_ICONS, typeLabel } from "./catalog"
import { canRender } from "./chart-view"
import type { ChartType } from "./spec"

// Only the types the backend found compatible with this result (`chart_types`) and the frontend can draw,
// grouped by what the chart is for.
export function ChartSwitcher({
  value,
  types,
  enabled,
  disabled,
  onChange,
}: {
  value: ChartType
  types: ChartType[]
  enabled?: ChartType[]
  disabled?: boolean
  onChange: (type: ChartType) => void
}) {
  const allowed = [...new Set([...types, "table" as const])].filter(
    (type) => canRender(type) && (!enabled || enabled.includes(type) || type === "table"),
  )
  const Icon = TYPE_ICONS[value]
  const groups = FAMILIES.map((family) => ({
    family,
    items: allowed.filter((type) => TYPE_FAMILIES[type] === family),
  })).filter((group) => group.items.length)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={`Loại biểu đồ: ${typeLabel(value)}. Đổi loại`}
        >
          <Icon data-icon="inline-start" />
          {typeLabel(value)}
          <ChevronDownIcon data-icon="inline-end" className="opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 w-56 overflow-y-auto">
        <DropdownMenuRadioGroup value={value} onValueChange={(next) => onChange(next as ChartType)}>
          {groups.map((group, index) => (
            <DropdownMenuGroup key={group.family}>
              {index > 0 && <DropdownMenuSeparator />}
              <DropdownMenuLabel className="text-xs text-muted-foreground">{group.family}</DropdownMenuLabel>
              {group.items.map((type) => {
                const ItemIcon = TYPE_ICONS[type]
                return (
                  <DropdownMenuRadioItem key={type} value={type}>
                    <ItemIcon />
                    {typeLabel(type)}
                  </DropdownMenuRadioItem>
                )
              })}
            </DropdownMenuGroup>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
