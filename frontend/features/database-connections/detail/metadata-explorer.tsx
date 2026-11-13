"use client"

import { useState } from "react"
import { CircleXIcon, EyeIcon, FolderIcon, KeyRoundIcon, RefreshCwIcon, SearchIcon, TableIcon } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

import { useColumns, useSchemas, useTables } from "../api"
import { dateFormat } from "../connection-format"
import { useConnectionId } from "./connection-layout"

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-9" />
      ))}
    </div>
  )
}

function ErrorAlert({ error }: { error: Error }) {
  return (
    <Alert variant="destructive">
      <CircleXIcon />
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  )
}

export function MetadataExplorer() {
  const connectionId = useConnectionId()
  const [schemaId, setSchemaId] = useState<string | null>(null)
  const [tableId, setTableId] = useState<string | null>(null)
  const [tableQuery, setTableQuery] = useState("")

  const schemas = useSchemas(connectionId)
  const schema = schemas.data?.find((s) => s.id === schemaId) ?? schemas.data?.[0] ?? null
  const tables = useTables(schema?.id ?? null)
  const visibleTables = (tables.data ?? []).filter((t) =>
    t.name.toLowerCase().includes(tableQuery.trim().toLowerCase()),
  )
  const table = tables.data?.find((t) => t.id === tableId) ?? visibleTables[0] ?? null
  const columns = useColumns(table?.id ?? null)

  if (schemas.error) return <ErrorAlert error={schemas.error} />

  if (schemas.data?.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <RefreshCwIcon />
          </EmptyMedia>
          <EmptyTitle>Chưa đồng bộ metadata</EmptyTitle>
          <EmptyDescription>Bấm &quot;Đồng bộ metadata&quot; ở đầu trang để đọc cấu trúc database nguồn.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[13rem_17rem_minmax(0,1fr)]">
      <Card size="sm">
        <CardHeader>
          <CardTitle>Schema</CardTitle>
          <CardDescription>
            {schema ? `Đồng bộ ${dateFormat.format(new Date(schema.last_synced_at))}` : " "}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!schemas.data ? (
            <ListSkeleton />
          ) : (
            <ScrollArea className="lg:h-[28rem]">
              <ItemGroup className="gap-1">
                {schemas.data.map((s) => (
                  <Item key={s.id} asChild size="xs" variant={s.id === schema?.id ? "muted" : "default"}>
                    <button
                      type="button"
                      aria-pressed={s.id === schema?.id}
                      onClick={() => {
                        setSchemaId(s.id)
                        setTableId(null)
                      }}
                    >
                      <ItemMedia variant="icon">
                        <FolderIcon />
                      </ItemMedia>
                      <ItemContent>
                        <ItemTitle>{s.name}</ItemTitle>
                      </ItemContent>
                    </button>
                  </Item>
                ))}
              </ItemGroup>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      <Card size="sm">
        <CardHeader>
          <CardTitle>Bảng và view</CardTitle>
          <CardDescription>{tables.data ? `${tables.data.length} đối tượng` : " "}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <InputGroup>
            <InputGroupAddon>
              <SearchIcon />
            </InputGroupAddon>
            <InputGroupInput
              placeholder="Lọc bảng..."
              aria-label="Lọc bảng"
              value={tableQuery}
              onChange={(e) => setTableQuery(e.target.value)}
            />
          </InputGroup>
          {tables.error ? (
            <ErrorAlert error={tables.error} />
          ) : !tables.data ? (
            <ListSkeleton />
          ) : visibleTables.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Không có bảng phù hợp.</p>
          ) : (
            <ScrollArea className="lg:h-[25rem]">
              <ItemGroup className="gap-1">
                {visibleTables.map((t) => (
                  <Item key={t.id} asChild size="xs" variant={t.id === table?.id ? "muted" : "default"}>
                    <button type="button" aria-pressed={t.id === table?.id} onClick={() => setTableId(t.id)}>
                      <ItemMedia variant="icon">
                        {t.table_type.toLowerCase().includes("view") ? <EyeIcon /> : <TableIcon />}
                      </ItemMedia>
                      <ItemContent>
                        <ItemTitle>{t.name}</ItemTitle>
                        <ItemDescription>{t.table_type}</ItemDescription>
                      </ItemContent>
                    </button>
                  </Item>
                ))}
              </ItemGroup>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      <Card size="sm" className="min-w-0">
        <CardHeader>
          <CardTitle className="truncate">{table ? `${schema?.name}.${table.name}` : "Cột"}</CardTitle>
          <CardDescription>
            {table?.description || (columns.data ? `${columns.data.length} cột` : " ")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!table ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Chọn một bảng để xem cột.</p>
          ) : columns.error ? (
            <ErrorAlert error={columns.error} />
          ) : !columns.data ? (
            <ListSkeleton />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">#</TableHead>
                  <TableHead>Tên cột</TableHead>
                  <TableHead>Kiểu dữ liệu</TableHead>
                  <TableHead>Null</TableHead>
                  <TableHead>Mặc định</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {columns.data.map((c) => (
                  <TableRow key={c.name}>
                    <TableCell className="text-muted-foreground tabular-nums">{c.ordinal_position}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 font-medium">
                        {c.name}
                        {c.is_primary_key && (
                          <Badge variant="secondary">
                            <KeyRoundIcon data-icon="inline-start" />
                            PK
                          </Badge>
                        )}
                      </div>
                      {c.description && <div className="text-muted-foreground">{c.description}</div>}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{c.data_type}</TableCell>
                    <TableCell className="text-muted-foreground">{c.is_nullable ? "Có" : "Không"}</TableCell>
                    <TableCell className="max-w-48 truncate font-mono text-xs text-muted-foreground">
                      {c.default_value ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
