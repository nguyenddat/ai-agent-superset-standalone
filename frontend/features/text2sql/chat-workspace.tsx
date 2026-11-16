"use client"

import { useMemo, useState } from "react"
import { HistoryIcon, InfoIcon, MessageSquareTextIcon, SquarePenIcon, UserIcon } from "lucide-react"
import { toast } from "sonner"

import { PromptComposer } from "@/components/prompt-composer"
import { Button } from "@/components/ui/button"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useConnection } from "@/features/database-connections/api"
import { FILL_SCREEN_ALWAYS, useConnectionId } from "@/features/database-connections/detail/connection-layout"
import { cn } from "@/lib/utils"

import { useSuggestions } from "./api"
import { AssistantTurn, UserTurn } from "./chat-turn"
import { ConversationHistory } from "./conversation-history"
import { useChat, type Turn } from "./use-chat"
import { useChatUserId } from "./user-id"

const MAX_LENGTH = 2000
const SUGGESTIONS = 4
const NONE = new Set<string>()

const errorText = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback)

// Signatures already picked for each join_ambiguous turn, read from the turns that continued it.
function chosenJoins(turns: Turn[]) {
  const chosen = new Map<string, Set<string>>()
  for (const turn of turns) {
    const choice = turn.request.choice
    if (choice) chosen.set(choice.turnId, new Set(chosen.get(choice.turnId)).add(choice.signature))
  }
  return chosen
}

function UserPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="max-w-48 text-muted-foreground">
          <UserIcon data-icon="inline-start" />
          <span className="truncate">{value || "Chưa đặt người dùng"}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <PopoverHeader>
          <PopoverTitle>Hỏi với tư cách</PopoverTitle>
          <PopoverDescription>
            Tên người dùng giúp AI áp dụng tri thức riêng của người đó, lưu lịch sử và nhớ các câu hỏi trước.
          </PopoverDescription>
        </PopoverHeader>
        <Field>
          <FieldLabel htmlFor="chat-user-id">Tên người dùng</FieldLabel>
          <Input
            id="chat-user-id"
            value={value}
            maxLength={255}
            placeholder="vd. alice"
            autoComplete="off"
            onChange={(event) => onChange(event.target.value)}
          />
          <FieldDescription>Chưa có đăng nhập nên tên này không được xác thực; trình duyệt sẽ nhớ nó.</FieldDescription>
        </Field>
      </PopoverContent>
    </Popover>
  )
}

export function ChatWorkspace() {
  const connectionId = useConnectionId()
  const { data: connection } = useConnection(connectionId)
  const [userId, setUserId] = useChatUserId()
  const user = userId.trim()
  const chat = useChat(connectionId, user)
  const { turns, status, busy, loading, conversationId } = chat
  const [draft, setDraft] = useState("")
  const [historyOpen, setHistoryOpen] = useState(false)
  const { data: suggestions } = useSuggestions(connectionId, user, SUGGESTIONS)
  const chosen = useMemo(() => chosenJoins(turns), [turns])
  const paused = connection?.is_active === false

  const ask = (question: string) => {
    setDraft("")
    chat.send(question)
  }

  const openConversation = (id: string) => {
    setHistoryOpen(false)
    if (id === conversationId) return
    chat.open(id).catch((error) => toast.error(errorText(error, "Không mở được cuộc trò chuyện.")))
  }

  const startNew = () => {
    setHistoryOpen(false)
    setDraft("")
    chat.clear()
  }

  const history = (
    <ConversationHistory
      connectionId={connectionId}
      userId={user}
      activeId={conversationId}
      onSelect={openConversation}
      onNew={startNew}
      onDeleted={chat.clear}
    />
  )

  const content = loading ? (
    <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
      <Spinner />
      Đang mở cuộc trò chuyện
    </div>
  ) : turns.length === 0 ? (
    <Empty className="flex-1">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <MessageSquareTextIcon />
        </EmptyMedia>
        <EmptyTitle>Hỏi dữ liệu bằng tiếng Việt</EmptyTitle>
        <EmptyDescription>
          AI tìm metric hoặc trường dữ liệu đã mô tả, tự dựng truy vấn chỉ đọc rồi giải thích kết quả. Dữ liệu cá nhân
          luôn được che trước khi hiển thị.
        </EmptyDescription>
      </EmptyHeader>
      {!!suggestions?.length && (
        <EmptyContent className="max-w-xl">
          <div className="flex flex-wrap justify-center gap-2">
            {suggestions.map(({ question }) => (
              <Button
                key={question}
                variant="outline"
                size="sm"
                className="h-auto max-w-full py-1.5 whitespace-normal"
                disabled={paused}
                onClick={() => ask(question)}
              >
                {question}
              </Button>
            ))}
          </div>
        </EmptyContent>
      )}
    </Empty>
  ) : (
    <MessageScrollerProvider autoScroll>
      <MessageScroller className="flex-1">
        <MessageScrollerViewport>
          <MessageScrollerContent className="mx-auto w-full max-w-4xl px-1 py-4">
            {!user && (
              <MessageScrollerItem messageId="intro">
                <Marker variant="separator">
                  <MarkerIcon>
                    <InfoIcon />
                  </MarkerIcon>
                  <MarkerContent>Chưa đặt người dùng nên AI không nhớ các câu trước và cuộc trò chuyện không được lưu</MarkerContent>
                </Marker>
              </MessageScrollerItem>
            )}
            {turns.flatMap((turn) => [
              <MessageScrollerItem key={`${turn.id}:q`} messageId={`${turn.id}:q`} scrollAnchor>
                <UserTurn turn={turn} />
              </MessageScrollerItem>,
              <MessageScrollerItem key={`${turn.id}:a`} messageId={`${turn.id}:a`}>
                <AssistantTurn
                  turn={turn}
                  connectionId={connectionId}
                  busy={busy || paused}
                  chosen={(turn.turnId && chosen.get(turn.turnId)) || NONE}
                  canChoose={!!user && !!turn.turnId && turn.conversationId === conversationId}
                  onAsk={ask}
                  onRetry={chat.retry}
                  onEdit={setDraft}
                  onChoose={chat.choose}
                  onRate={(target, rating) =>
                    chat.rate(target, rating).catch((error) => toast.error(errorText(error, "Không lưu được đánh giá.")))
                  }
                />
              </MessageScrollerItem>,
            ])}
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton />
      </MessageScroller>
    </MessageScrollerProvider>
  )

  return (
    <div className={cn("flex min-h-96 gap-4", FILL_SCREEN_ALWAYS)}>
      <aside aria-label="Cuộc trò chuyện đã lưu" className="hidden w-64 shrink-0 flex-col border-r pr-3 lg:flex">
        {history}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {content}
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-1.5 pt-2">
          <PromptComposer
            value={draft}
            onValueChange={setDraft}
            onSubmit={ask}
            onStop={chat.stop}
            status={status}
            maxLength={MAX_LENGTH}
            autoFocus
            placeholder="Hỏi về dữ liệu, vd. doanh thu theo vùng năm nay"
            disabled={paused}
            disabledReason="Kết nối đang tạm dừng nên chưa thể hỏi dữ liệu."
            toolbar={
              <>
                <UserPicker value={userId} onChange={setUserId} />
                <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SheetTrigger asChild>
                        <Button variant="ghost" size="icon-sm" className="text-muted-foreground lg:hidden" aria-label="Lịch sử trò chuyện">
                          <HistoryIcon />
                        </Button>
                      </SheetTrigger>
                    </TooltipTrigger>
                    <TooltipContent>Lịch sử trò chuyện</TooltipContent>
                  </Tooltip>
                  <SheetContent side="left" className="w-80 gap-0">
                    <SheetHeader>
                      <SheetTitle>Lịch sử trò chuyện</SheetTitle>
                      <SheetDescription className="sr-only">Mở lại hoặc quản lý các cuộc trò chuyện đã lưu.</SheetDescription>
                    </SheetHeader>
                    <div className="min-h-0 flex-1 px-4 pb-4">{history}</div>
                  </SheetContent>
                </Sheet>
                {turns.length > 0 && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="icon-sm" className="text-muted-foreground" aria-label="Cuộc trò chuyện mới" onClick={startNew}>
                        <SquarePenIcon />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Cuộc trò chuyện mới</TooltipContent>
                  </Tooltip>
                )}
              </>
            }
          />
          <p className="text-center text-xs text-muted-foreground">
            AI có thể hiểu sai câu hỏi. Kiểm tra SQL và các quy tắc đã áp dụng trước khi dùng số liệu.
          </p>
        </div>
      </div>
    </div>
  )
}
