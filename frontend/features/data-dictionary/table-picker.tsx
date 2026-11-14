"use client"

import { useState } from "react"
import { ChevronsUpDownIcon, EyeIcon, TableIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

import type { DictionarySummary } from "./types"

export function TablePicker({
  summary,
  tableId,
  label,
  onSelect,
}: {
  summary: DictionarySummary
  tableId: string
  label: string
  onSelect: (tableId: string) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          role="combobox"
          aria-expanded={open}
          aria-label="Chọn bảng"
          className="-ml-2 h-auto max-w-full min-w-0 px-2 py-1 text-base font-semibold"
        >
          <span className="truncate">{label}</span>
          <ChevronsUpDownIcon data-icon="inline-end" className="text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 max-w-[calc(100vw-2rem)] p-0">
        <Command>
          <CommandInput placeholder="Tìm bảng..." />
          <CommandList className="max-h-96">
            <CommandEmpty>Không có bảng phù hợp.</CommandEmpty>
            {summary.schemas.map((schema) => (
              <CommandGroup key={schema.schema_id} heading={schema.schema_name}>
                {schema.tables.map((table) => (
                  <CommandItem
                    key={table.table_id}
                    value={`${schema.schema_name}.${table.table_name}`}
                    keywords={[table.display_name]}
                    data-checked={table.table_id === tableId}
                    onSelect={() => {
                      setOpen(false)
                      onSelect(table.table_id)
                    }}
                  >
                    {table.table_type.toLowerCase().includes("view") ? <EyeIcon /> : <TableIcon />}
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate">{table.display_name}</span>
                      {table.display_name !== table.table_name && (
                        <span className="truncate font-mono text-xs text-muted-foreground">{table.table_name}</span>
                      )}
                    </div>
                    <Badge variant={table.is_saved ? "secondary" : "outline"} className="tabular-nums">
                      {table.described_column_count}/{table.column_count}
                    </Badge>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
          <p className="border-t px-3 py-2 text-xs text-muted-foreground">
            {summary.described_table_count}/{summary.table_count} bảng đã mô tả · số trên mỗi bảng: cột đã mô tả / tổng
            số cột
          </p>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
