"use client"

import { useMemo } from "react"
import { HistoryIcon } from "lucide-react"
import { toast } from "sonner"

import { ChatHistory } from "@/components/chat-history"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import { deleteConversation, updateConversation, useConversations, type ConversationChange } from "./api"

type HistoryProps = {
  connectionId: string
  userId: string
  activeId?: string
  onSelect: (id: string) => void
  onNew: () => void
  // The open conversation was deleted, so the screen must not keep adding turns to it.
  onDeleted: (id: string) => void
}

const failed = (error: unknown) => toast.error(error instanceof Error ? error.message : "Không lưu được thay đổi.")

export function ConversationHistory({ connectionId, userId, activeId, onSelect, onNew, onDeleted }: HistoryProps) {
  const { data, error, isLoading } = useConversations(connectionId, userId)
  const chats = useMemo(
    () =>
      (data ?? []).map((item) => ({
        id: item.id,
        title: item.title,
        updatedAt: Date.parse(item.last_message_at ?? item.updated_at),
        pinned: item.is_pinned,
      })),
    [data],
  )

  if (!userId) {
    return (
      <Empty className="p-4">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HistoryIcon />
          </EmptyMedia>
          <EmptyTitle>Chưa lưu lịch sử</EmptyTitle>
          <EmptyDescription>Đặt tên người dùng ở ô hỏi để lưu các cuộc trò chuyện và để AI nhớ câu hỏi trước.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  if (isLoading) {
    return (
      <div className="flex flex-col gap-2 p-1">
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    )
  }
  if (error) return <p className="p-2 text-sm text-muted-foreground">{error.message}</p>

  const change = (id: string, value: ConversationChange) => updateConversation(connectionId, userId, id, value).catch(failed)

  return (
    <ChatHistory
      className="h-full"
      chats={chats}
      activeId={activeId}
      onSelect={onSelect}
      onNew={onNew}
      onRename={(id, title) => void change(id, { title })}
      onPin={(id, pinned) => void change(id, { is_pinned: pinned })}
      onDelete={(id) => {
        if (id === activeId) onDeleted(id)
        deleteConversation(connectionId, userId, id).catch(failed)
      }}
    />
  )
}
