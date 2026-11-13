"use client"

import { useState } from "react"
import { CircleCheckIcon, CircleXIcon, EyeIcon, EyeOffIcon } from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldContent, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { ApiError } from "@/lib/api"

import { createConnection, testConnection, updateConnection, useDialects } from "./api"
import { buildConnectionUri } from "./connection-uri"
import type { ConnectionTestResult, DatabaseConnection } from "./types"

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  connection?: DatabaseConnection | null
}

export function ConnectionFormDialog({ open, onOpenChange, connection }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{connection ? "Sửa kết nối" : "Thêm kết nối"}</DialogTitle>
          <DialogDescription>
            {connection
              ? "Chỉ những trường bạn thay đổi mới được gửi lên. URI được mã hóa khi lưu."
              : "Đăng ký một database nguồn. URI được mã hóa khi lưu và không bao giờ hiển thị lại."}
          </DialogDescription>
        </DialogHeader>
        <ConnectionForm connection={connection ?? null} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}

function ConnectionForm({ connection, onDone }: { connection: DatabaseConnection | null; onDone: () => void }) {
  const { data: dialects } = useDialects()
  const [name, setName] = useState(connection?.name ?? "")
  const [dialectKey, setDialectKey] = useState("")
  const [inputMode, setInputMode] = useState<"parts" | "uri">(connection ? "uri" : "parts")
  const [uri, setUri] = useState("")
  const [host, setHost] = useState("")
  const [port, setPort] = useState("5432")
  const [database, setDatabase] = useState("")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [inputError, setInputError] = useState("")
  const [isActive, setIsActive] = useState(connection?.is_active ?? true)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const dialect =
    dialects?.find((d) => `${d.dialect}:${d.driver}` === dialectKey) ??
    dialects?.find((d) => d.dialect === connection?.dialect) ??
    dialects?.[0]
  const nameTaken = error?.status === 409
  const uriInvalid = error?.status === 422 || error?.status === 503
  const partsTouched = !!(host || database || username || password || port !== "5432")
  const connectionUri = inputMode === "uri"
    ? uri.trim()
    : dialect && partsTouched
      ? buildConnectionUri(dialect.dialect, dialect.driver, { host, port, database, username, password })
      : ""

  function updatePart(setter: (value: string) => void, value: string) {
    setter(value)
    setInputError("")
    setTestResult(null)
    setError(null)
  }

  async function handleTest() {
    if (!dialect || !connectionUri) {
      setInputError("Điền máy chủ, cổng, tên database và người dùng hợp lệ trước khi kiểm tra.")
      return
    }
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await testConnection({ dialect: dialect.dialect, driver: dialect.driver, uri: connectionUri }))
    } catch (e) {
      setTestResult({ ok: false, message: e instanceof Error ? e.message : String(e) })
    } finally {
      setTesting(false)
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if ((!connection || (inputMode === "parts" && partsTouched) || (inputMode === "uri" && uri.trim())) && !connectionUri) {
      setInputError("Điền máy chủ, cổng, tên database và người dùng hợp lệ, hoặc nhập URI kết nối.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (connection) {
        const changes: Parameters<typeof updateConnection>[1] = {}
        if (name.trim() !== connection.name) changes.name = name.trim()
        if (isActive !== connection.is_active) changes.is_active = isActive
        if (connectionUri) changes.uri = connectionUri
        if (Object.keys(changes).length) await updateConnection(connection.id, changes)
        toast.success(`Đã cập nhật kết nối "${name.trim()}".`)
      } else {
        if (!dialect) return
        await createConnection({ name: name.trim(), dialect: dialect.dialect, driver: dialect.driver, uri: connectionUri! })
        toast.success(`Đã thêm kết nối "${name.trim()}".`)
      }
      onDone()
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <FieldGroup>
        <Field data-invalid={nameTaken || undefined}>
          <FieldLabel htmlFor="connection-name">Tên kết nối</FieldLabel>
          <Input
            id="connection-name"
            required
            maxLength={255}
            placeholder="VD: Kho bán hàng"
            value={name}
            aria-invalid={nameTaken || undefined}
            onChange={(e) => setName(e.target.value)}
          />
          {nameTaken && <FieldError>{error.message}</FieldError>}
        </Field>

        <Field data-disabled={connection ? true : undefined}>
          <FieldLabel htmlFor="connection-dialect">Loại database</FieldLabel>
          <Select
            value={dialect ? `${dialect.dialect}:${dialect.driver}` : ""}
            onValueChange={setDialectKey}
            disabled={!!connection || !dialects}
          >
            <SelectTrigger id="connection-dialect" className="w-full">
              <SelectValue placeholder="Đang tải..." />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {dialects?.map((d) => (
                  <SelectItem key={`${d.dialect}:${d.driver}`} value={`${d.dialect}:${d.driver}`}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {connection && <FieldDescription>Không đổi được loại database của kết nối đã tạo.</FieldDescription>}
        </Field>

        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 text-sm font-medium">Cách nhập thông tin kết nối</legend>
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
            <button type="button" aria-pressed={inputMode === "parts"}
              className={`rounded-md px-3 py-2 text-sm ${inputMode === "parts" ? "bg-background font-medium" : "text-muted-foreground"}`}
              onClick={() => { setInputMode("parts"); setInputError(""); setTestResult(null); setError(null) }}>
              Từng thành phần
            </button>
            <button type="button" aria-pressed={inputMode === "uri"}
              className={`rounded-md px-3 py-2 text-sm ${inputMode === "uri" ? "bg-background font-medium" : "text-muted-foreground"}`}
              onClick={() => { setInputMode("uri"); setInputError(""); setTestResult(null); setError(null) }}>
              URI đầy đủ
            </button>
          </div>

          {inputMode === "parts" ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="connection-host">Máy chủ</FieldLabel>
                <Input id="connection-host" value={host} required={!connection} autoComplete="off"
                  placeholder="db.example.com" onChange={(e) => updatePart(setHost, e.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="connection-port">Cổng</FieldLabel>
                <Input id="connection-port" type="number" min={1} max={65535} value={port} required={!connection}
                  onChange={(e) => updatePart(setPort, e.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="connection-database">Tên database</FieldLabel>
                <Input id="connection-database" value={database} required={!connection} autoComplete="off"
                  placeholder="analytics" onChange={(e) => updatePart(setDatabase, e.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="connection-username">Người dùng</FieldLabel>
                <Input id="connection-username" value={username} required={!connection} autoComplete="username"
                  placeholder="reader" onChange={(e) => updatePart(setUsername, e.target.value)} />
              </Field>
              <Field className="sm:col-span-2">
                <FieldLabel htmlFor="connection-password">Mật khẩu</FieldLabel>
                <InputGroup>
                  <InputGroupInput id="connection-password" type={showPassword ? "text" : "password"}
                    value={password} autoComplete="new-password" placeholder="Mật khẩu database nguồn"
                    onChange={(e) => updatePart(setPassword, e.target.value)} />
                  <InputGroupAddon align="inline-end">
                    <InputGroupButton size="icon-xs" type="button"
                      aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                      onClick={() => setShowPassword((value) => !value)}>
                      {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                    </InputGroupButton>
                  </InputGroupAddon>
                </InputGroup>
              </Field>
            </div>
          ) : (
            <Field data-invalid={uriInvalid || undefined}>
              <FieldLabel htmlFor="connection-uri">URI kết nối</FieldLabel>
              <Input id="connection-uri" autoComplete="off" spellCheck={false}
                data-1p-ignore data-lpignore="true" data-bwignore required={!connection}
                placeholder={connection ? "Để trống nếu giữ nguyên URI hiện tại" : "postgresql+psycopg://user:password@host:5432/db"}
                value={uri} aria-invalid={uriInvalid || undefined}
                onChange={(e) => updatePart(setUri, e.target.value)} />
            </Field>
          )}
          {inputError && <FieldError>{inputError}</FieldError>}
          {uriInvalid ? <FieldError>{error.message}</FieldError> : (
            <FieldDescription>Backend kiểm tra kết nối trước khi lưu. Mật khẩu và URI không được hiển thị lại sau khi lưu.</FieldDescription>
          )}
        </fieldset>

        {connection && (
          <Field orientation="horizontal">
            <FieldContent>
              <FieldLabel htmlFor="connection-active">Đang hoạt động</FieldLabel>
              <FieldDescription>Kết nối tạm dừng sẽ không đồng bộ được metadata.</FieldDescription>
            </FieldContent>
            <Switch id="connection-active" checked={isActive} onCheckedChange={setIsActive} />
          </Field>
        )}
      </FieldGroup>

      {testResult && (
        <Alert variant={testResult.ok ? "default" : "destructive"}>
          {testResult.ok ? <CircleCheckIcon /> : <CircleXIcon />}
          <AlertDescription>{testResult.message}</AlertDescription>
        </Alert>
      )}
      {error && !nameTaken && !uriInvalid && (
        <Alert variant="destructive">
          <CircleXIcon />
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" disabled={!connectionUri || !dialect || testing} onClick={handleTest}>
          {testing && <Spinner data-icon="inline-start" />}
          Kiểm tra kết nối
        </Button>
        <div className="flex gap-2 sm:ml-auto">
          <DialogClose asChild>
            <Button type="button" variant="ghost">
              Hủy
            </Button>
          </DialogClose>
          <Button type="submit" disabled={saving || !name.trim() || (!connection && (!connectionUri || !dialect))}>
            {saving && <Spinner data-icon="inline-start" />}
            {connection ? "Lưu thay đổi" : "Thêm kết nối"}
          </Button>
        </div>
      </DialogFooter>
    </form>
  )
}
