"use client"

import { useState } from "react"
import { ChevronLeftIcon, ChevronsUpDownIcon, EyeIcon, KeyRoundIcon, TableIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Spinner } from "@/components/ui/spinner"

import { useDictionarySummary, useTableDictionary } from "./api"
import type { ReferencedColumn } from "./types"

type ReferencePickerProps = {
  id: string
  connectionId: string
  columnId: string
  value: ReferencedColumn | null
  onChange: (value: ReferencedColumn | null) => void
}

export function ReferencePicker({ id, connectionId, columnId, value, onChange }: ReferencePickerProps) {
  const [open, setOpen] = useState(false)
  const [tableId, setTableId] = useState<string | null>(null)

  const choose = (next: ReferencedColumn | null) => {
    onChange(next)
    setOpen(false)
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) setTableId(value?.table_id ?? null)
        setOpen(next)
      }}
    >
      <PopoverTrigger asChild>
        <Button id={id} variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between font-normal">
          {value ? (
            <span className="truncate font-mono text-xs">
              {value.table_name}.{value.column_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Không tham chiếu</span>
          )}
          <ChevronsUpDownIcon data-icon="inline-end" className="text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 max-w-[calc(100vw-2rem)] p-0">
        {tableId ? (
          <ColumnList
            tableId={tableId}
            columnId={columnId}
            value={value}
            onBack={() => setTableId(null)}
            onSelect={choose}
          />
        ) : (
          <TableList connectionId={connectionId} value={value} onSelect={setTableId} onClear={() => choose(null)} />
        )}
      </PopoverContent>
    </Popover>
  )
}

function TableList({
  connectionId,
  value,
  onSelect,
  onClear,
}: {
  connectionId: string
  value: ReferencedColumn | null
  onSelect: (tableId: string) => void
  onClear: () => void
}) {
  const { data: summary } = useDictionarySummary(connectionId)

  return (
    <Command>
      <CommandInput placeholder="Tìm bảng được tham chiếu..." />
      <CommandList className="max-h-80">
        <CommandEmpty>{summary ? "Không có bảng phù hợp." : <Spinner className="mx-auto" />}</CommandEmpty>
        {value && (
          <CommandGroup>
            <CommandItem value="__clear" onSelect={onClear}>
              <XIcon />
              Bỏ tham chiếu
            </CommandItem>
          </CommandGroup>
        )}
        {summary?.schemas.map((schema) => (
          <CommandGroup key={schema.schema_id} heading={schema.schema_name}>
            {schema.tables.map((table) => (
              <CommandItem
                key={table.table_id}
                value={`${schema.schema_name}.${table.table_name}`}
                keywords={[table.display_name]}
                data-checked={table.table_id === value?.table_id}
                onSelect={() => onSelect(table.table_id)}
              >
                {table.table_type.toLowerCase().includes("view") ? <EyeIcon /> : <TableIcon />}
                <span className="flex min-w-0 flex-1 items-baseline justify-between gap-2">
                  <span className="truncate">{table.display_name}</span>
                  {table.display_name !== table.table_name && (
                    <span className="truncate font-mono text-xs text-muted-foreground">{table.table_name}</span>
                  )}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </Command>
  )
}

function ColumnList({
  tableId,
  columnId,
  value,
  onBack,
  onSelect,
}: {
  tableId: string
  columnId: string
  value: ReferencedColumn | null
  onBack: () => void
  onSelect: (value: ReferencedColumn) => void
}) {
  const { data: dictionary } = useTableDictionary(tableId)
  const columns = dictionary?.columns.filter((column) => column.column_id !== columnId) ?? []

  return (
    <Command>
      <div className="flex items-center gap-1 border-b p-1">
        <Button variant="ghost" size="icon-xs" aria-label="Chọn bảng khác" onClick={onBack}>
          <ChevronLeftIcon />
        </Button>
        <span className="truncate text-sm font-medium">{dictionary?.display_name ?? "..."}</span>
      </div>
      <CommandInput placeholder="Tìm cột..." />
      <CommandList className="max-h-80">
        <CommandEmpty>{dictionary ? "Không có cột phù hợp." : <Spinner className="mx-auto" />}</CommandEmpty>
        {dictionary && (
          <CommandGroup>
            {columns.map((column) => (
              <CommandItem
                key={column.column_id}
                value={column.name}
                keywords={[column.display_name]}
                data-checked={column.column_id === value?.column_id}
                onSelect={() =>
                  onSelect({
                    column_id: column.column_id,
                    table_id: dictionary.table_id,
                    schema_name: dictionary.schema_name,
                    table_name: dictionary.table_name,
                    column_name: column.name,
                  })
                }
              >
                {(column.is_primary_key ?? column.source_is_primary_key) ? <KeyRoundIcon /> : <span className="size-4" />}
                <span className="flex min-w-0 flex-1 items-baseline gap-2">
                  <span className="truncate font-mono text-xs">{column.name}</span>
                  {column.display_name !== column.name && (
                    <span className="truncate text-muted-foreground">{column.display_name}</span>
                  )}
                </span>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">{column.data_type}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </Command>
  )
}
