"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import {
  CircleXIcon,
  DatabaseIcon,
  LayoutGridIcon,
  ListIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  SearchXIcon,
  Trash2Icon,
} from "lucide-react"

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

import { useConnections } from "./api"
import { ConnectionFormDialog } from "./connection-form-dialog"
import { dateFormat, describe, StatusBadge } from "./connection-format"
import { ConnectionStats } from "./connection-stats"
import { DeleteConnectionDialog } from "./delete-connection-dialog"
import { syncWithToast } from "./sync-with-toast"
import type { DatabaseConnection } from "./types"

type SortKey = "name" | "updated"
type ViewMode = "grid" | "list"

type Actions = {
  syncing: boolean
  onSync: () => void
  onEdit: () => void
  onDelete: () => void
}

function ConnectionMenu({ connection, syncing, onSync, onEdit, onDelete }: Actions & { connection: DatabaseConnection }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Thao tác với ${connection.name}`}>
          {syncing ? <Spinner /> : <MoreHorizontalIcon />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuGroup>
          <DropdownMenuItem disabled={syncing || !connection.is_active} onSelect={onSync}>
            <RefreshCwIcon />
            Đồng bộ metadata
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onEdit}>
            <PencilIcon />
            Sửa kết nối
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem variant="destructive" onSelect={onDelete}>
            <Trash2Icon />
            Xóa
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ConnectionCard({ connection, ...actions }: Actions & { connection: DatabaseConnection }) {
  return (
    <Card className="relative transition-colors has-[a:hover]:bg-muted/50">
      <CardHeader>
        <CardTitle className="flex min-w-0 items-center gap-2">
          <DatabaseIcon className="size-4 shrink-0 text-muted-foreground" />
          <Link href={`/connections/${connection.id}`} className="truncate after:absolute after:inset-0">
            {connection.name}
          </Link>
        </CardTitle>
        <CardDescription>{describe(connection)}</CardDescription>
        <CardAction className="relative">
          <ConnectionMenu connection={connection} {...actions} />
        </CardAction>
      </CardHeader>
      <CardFooter className="justify-between gap-2 text-muted-foreground">
        <span className="truncate">Cập nhật {dateFormat.format(new Date(connection.updated_at))}</span>
        <StatusBadge active={connection.is_active} />
      </CardFooter>
    </Card>
  )
}

function ConnectionRow({ connection, ...actions }: Actions & { connection: DatabaseConnection }) {
  return (
    <Item variant="outline" className="relative has-[a:hover]:bg-muted/50">
      <ItemMedia variant="icon">
        <DatabaseIcon />
      </ItemMedia>
      <ItemContent>
        <ItemTitle>
          <Link href={`/connections/${connection.id}`} className="after:absolute after:inset-0">
            {connection.name}
          </Link>
        </ItemTitle>
        <ItemDescription>
          {describe(connection)} · Cập nhật {dateFormat.format(new Date(connection.updated_at))}
        </ItemDescription>
      </ItemContent>
      <ItemActions className="relative">
        <StatusBadge active={connection.is_active} />
        <ConnectionMenu connection={connection} {...actions} />
      </ItemActions>
    </Item>
  )
}

function LoadingGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-32 rounded-xl" />
      ))}
    </div>
  )
}

export function ConnectionsView() {
  const { data: connections, error, isLoading, mutate } = useConnections()
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState<SortKey>("name")
  const [view, setView] = useState<ViewMode>("grid")
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<DatabaseConnection | null>(null)
  const [deleting, setDeleting] = useState<DatabaseConnection | null>(null)
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set())

  const visible = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return (connections ?? [])
      .filter((c) => !keyword || c.name.toLowerCase().includes(keyword) || c.dialect.toLowerCase().includes(keyword))
      .sort((a, b) =>
        sort === "name" ? a.name.localeCompare(b.name, "vi") : b.updated_at.localeCompare(a.updated_at),
      )
  }, [connections, query, sort])

  function openForm(connection: DatabaseConnection | null) {
    setEditing(connection)
    setFormOpen(true)
  }

  async function handleSync(connection: DatabaseConnection) {
    setSyncingIds((ids) => new Set(ids).add(connection.id))
    try {
      await syncWithToast(connection)
    } finally {
      setSyncingIds((ids) => {
        const next = new Set(ids)
        next.delete(connection.id)
        return next
      })
    }
  }

  function actionsFor(connection: DatabaseConnection): Actions {
    return {
      syncing: syncingIds.has(connection.id),
      onSync: () => handleSync(connection),
      onEdit: () => openForm(connection),
      onDelete: () => setDeleting(connection),
    }
  }

  let content: React.ReactNode
  if (error) {
    content = (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertTitle>Không tải được danh sách kết nối</AlertTitle>
        <AlertDescription>{error.message}</AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => mutate()}>
            Thử lại
          </Button>
        </AlertAction>
      </Alert>
    )
  } else if (isLoading || !connections) {
    content = <LoadingGrid />
  } else if (connections.length === 0) {
    content = (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <DatabaseIcon />
          </EmptyMedia>
          <EmptyTitle>Chưa có kết nối nào</EmptyTitle>
          <EmptyDescription>Thêm database nguồn đầu tiên để bắt đầu đồng bộ và khám phá metadata.</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button onClick={() => openForm(null)}>
            <PlusIcon data-icon="inline-start" />
            Thêm kết nối
          </Button>
        </EmptyContent>
      </Empty>
    )
  } else if (visible.length === 0) {
    content = (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <SearchXIcon />
          </EmptyMedia>
          <EmptyTitle>Không tìm thấy kết nối</EmptyTitle>
          <EmptyDescription>Không có kết nối nào khớp với &quot;{query}&quot;.</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button variant="outline" onClick={() => setQuery("")}>
            Xóa tìm kiếm
          </Button>
        </EmptyContent>
      </Empty>
    )
  } else {
    content = (
      <>
        {view === "grid" ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {visible.map((connection) => (
              <ConnectionCard key={connection.id} connection={connection} {...actionsFor(connection)} />
            ))}
          </div>
        ) : (
          <ItemGroup className="gap-2">
            {visible.map((connection) => (
              <ConnectionRow key={connection.id} connection={connection} {...actionsFor(connection)} />
            ))}
          </ItemGroup>
        )}
        <p className="text-center text-sm text-muted-foreground">
          Hiển thị {visible.length} trên {connections.length} kết nối
        </p>
      </>
    )
  }

  return (
    <>
      <ConnectionStats />

      <section className="flex flex-col gap-6">
        <div className="flex flex-wrap items-center gap-3">
          <InputGroup className="w-full sm:w-80">
            <InputGroupAddon>
              <SearchIcon />
            </InputGroupAddon>
            <InputGroupInput
              placeholder="Tìm kết nối..."
              aria-label="Tìm kết nối"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </InputGroup>
          <Select value={sort} onValueChange={(value) => setSort(value as SortKey)}>
            <SelectTrigger className="w-48" aria-label="Sắp xếp">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="name">Sắp xếp theo tên</SelectItem>
                <SelectItem value="updated">Mới cập nhật</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          <ToggleGroup
            type="single"
            variant="outline"
            value={view}
            onValueChange={(value) => value && setView(value as ViewMode)}
            className="sm:ml-auto"
          >
            <ToggleGroupItem value="grid" aria-label="Dạng lưới">
              <LayoutGridIcon />
            </ToggleGroupItem>
            <ToggleGroupItem value="list" aria-label="Dạng danh sách">
              <ListIcon />
            </ToggleGroupItem>
          </ToggleGroup>
          <Button onClick={() => openForm(null)}>
            <PlusIcon data-icon="inline-start" />
            Thêm kết nối
          </Button>
        </div>
        {content}
      </section>

      <ConnectionFormDialog open={formOpen} onOpenChange={setFormOpen} connection={editing} />
      <DeleteConnectionDialog connection={deleting} onOpenChange={(open) => !open && setDeleting(null)} />
    </>
  )
}
