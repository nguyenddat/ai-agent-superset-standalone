"use client"

import { useState } from "react"
import { ArrowLeftIcon, ArrowRightIcon, CircleCheckIcon, CircleXIcon, EyeIcon, EyeOffIcon } from "lucide-react"
import { toast } from "sonner"

import { Steps } from "@/components/steps"
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
import { ConnectionScopeStep } from "./connection-scope-step"
import { buildConnectionUri } from "./connection-uri"
import { emptyScope, SCOPE_FIELDS, sameScope, type MetadataScope } from "./metadata-scope"
import { syncWithToast } from "./sync-with-toast"
import type { ConnectionTestResult, DatabaseConnection } from "./types"

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  connection?: DatabaseConnection | null
}

const STEPS = [
  { label: "Kết nối", description: "Thông tin đăng nhập database" },
  { label: "Phạm vi metadata", description: "Lọc schema và bảng" },
]

const keepOpen = (event: Event) => event.preventDefault()

export function ConnectionFormDialog({ open, onOpenChange, connection }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Only the close button and Hủy close the form, so a stray click or Escape never loses what was typed. */}
      <DialogContent
        className="max-h-[90vh] overflow-y-auto sm:max-w-2xl"
        onInteractOutside={keepOpen}
        onEscapeKeyDown={keepOpen}
      >
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
  const [step, setStep] = useState(0)
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
  const [scope, setScope] = useState<MetadataScope>(() =>
    connection ? Object.fromEntries(SCOPE_FIELDS.map((field) => [field, connection[field]])) as MetadataScope : emptyScope(),
  )
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
      ? (buildConnectionUri(dialect.dialect, dialect.driver, { host, port, database, username, password }) ?? "")
      : ""
  const uriRequired = !connection || (inputMode === "parts" && partsTouched) || (inputMode === "uri" && !!uri.trim())

  function updatePart(setter: (value: string) => void, value: string) {
    setter(value)
    setInputError("")
    setTestResult(null)
    setError(null)
  }

  async function runTest() {
    if (!dialect || !connectionUri) return null
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testConnection({ dialect: dialect.dialect, driver: dialect.driver, uri: connectionUri })
      setTestResult(result)
      return result
    } catch (e) {
      const result = { ok: false, message: e instanceof Error ? e.message : String(e) }
      setTestResult(result)
      return result
    } finally {
      setTesting(false)
    }
  }

  async function handleTest() {
    if (!dialect || !connectionUri) {
      setInputError("Điền máy chủ, cổng, tên database và người dùng hợp lệ trước khi kiểm tra.")
      return
    }
    await runTest()
  }

  // Step 1 is done when the connection details are complete and, when new ones were typed, the source answers.
  async function handleNext() {
    if (uriRequired && !connectionUri) {
      setInputError("Điền máy chủ, cổng, tên database và người dùng hợp lệ, hoặc nhập URI kết nối.")
      return
    }
    if (connectionUri && !testResult?.ok) {
      const result = await runTest()
      if (!result?.ok) return
    }
    setError(null)
    setStep(1)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      if (connection) {
        const changes: Parameters<typeof updateConnection>[1] = {}
        if (name.trim() !== connection.name) changes.name = name.trim()
        if (isActive !== connection.is_active) changes.is_active = isActive
        if (connectionUri) changes.uri = connectionUri
        for (const field of SCOPE_FIELDS) {
          if (JSON.stringify(scope[field]) !== JSON.stringify(connection[field])) changes[field] = scope[field]
        }
        const updated = Object.keys(changes).length ? await updateConnection(connection.id, changes) : connection
        const scopeChanged = !sameScope(scope, connection)
        toast.success(`Đã cập nhật kết nối "${name.trim()}".`, {
          description: scopeChanged ? "Phạm vi metadata đã đổi; đồng bộ lại để cập nhật danh sách bảng." : undefined,
          action: scopeChanged && updated.is_active
            ? { label: "Đồng bộ ngay", onClick: () => void syncWithToast(updated) }
            : undefined,
        })
      } else {
        if (!dialect) return
        const created = await createConnection({
          name: name.trim(),
          dialect: dialect.dialect,
          driver: dialect.driver,
          uri: connectionUri,
          ...scope,
        })
        toast.success(`Đã thêm kết nối "${created.name}".`, {
          description: "Đồng bộ metadata để lấy schema và bảng theo phạm vi đã chọn.",
          action: { label: "Đồng bộ ngay", onClick: () => void syncWithToast(created) },
        })
      }
      onDone()
    } catch (e) {
      const apiError = e instanceof ApiError ? e : new ApiError(0, String(e))
      setError(apiError)
      // Name and connection errors belong to the first step: show them next to their field.
      if (apiError.status === 409 || apiError.status === 422 || apiError.status === 503) setStep(0)
    } finally {
      setSaving(false)
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (step === 0) void handleNext()
    else void handleSave()
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <Steps steps={STEPS} current={step} onStepClick={(index) => setStep(index)} />

      {step === 0 ? (
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
              <FieldDescription>
                {connection
                  ? "Nhập thông tin mới chỉ khi muốn đổi; kết nối được kiểm tra trước khi sang bước tiếp theo."
                  : "Kết nối được kiểm tra trước khi sang bước tiếp theo. Mật khẩu và URI không được hiển thị lại sau khi lưu."}
              </FieldDescription>
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
      ) : (
        <ConnectionScopeStep scope={scope} onChange={setScope} />
      )}

      {step === 0 && testResult && (
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
        {step === 0 ? (
          <Button type="button" variant="outline" disabled={!connectionUri || !dialect || testing} onClick={handleTest}>
            {testing && <Spinner data-icon="inline-start" />}
            Kiểm tra kết nối
          </Button>
        ) : (
          <Button type="button" variant="outline" onClick={() => setStep(0)}>
            <ArrowLeftIcon data-icon="inline-start" />
            Quay lại
          </Button>
        )}
        <div className="flex gap-2 sm:ml-auto">
          <DialogClose asChild>
            <Button type="button" variant="ghost">
              Hủy
            </Button>
          </DialogClose>
          {step === 0 ? (
            <Button type="submit" disabled={testing || !name.trim() || (!connection && (!connectionUri || !dialect))}>
              {testing && <Spinner data-icon="inline-start" />}
              Tiếp tục
              {!testing && <ArrowRightIcon data-icon="inline-end" />}
            </Button>
          ) : (
            <Button type="submit" disabled={saving}>
              {saving && <Spinner data-icon="inline-start" />}
              {connection ? "Lưu thay đổi" : "Thêm kết nối"}
            </Button>
          )}
        </div>
      </DialogFooter>
    </form>
  )
}
