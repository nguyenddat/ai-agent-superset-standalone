"use client"

import { CirclePauseIcon, CirclePlayIcon, PlugIcon } from "lucide-react"

import { Card, CardAction, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

import { useConnections } from "./api"

export function ConnectionStats() {
  const { data, error } = useConnections()
  const active = data?.filter((c) => c.is_active).length ?? 0
  const stats = [
    { label: "Kết nối", value: data?.length, icon: PlugIcon, detail: "Database nguồn đã đăng ký" },
    { label: "Đang hoạt động", value: active, icon: CirclePlayIcon, detail: "Có thể đồng bộ metadata" },
    { label: "Tạm dừng", value: (data?.length ?? 0) - active, icon: CirclePauseIcon, detail: "Không đồng bộ được" },
  ]

  return (
    <section aria-label="Tổng quan kết nối" className="grid gap-4 sm:grid-cols-3">
      {stats.map(({ label, value, icon: Icon, detail }) => (
        <Card key={label}>
          <CardHeader>
            <CardDescription>{label}</CardDescription>
            <CardTitle className="text-3xl font-semibold tabular-nums">
              {error ? "—" : data ? value : <Skeleton className="h-9 w-12" />}
            </CardTitle>
            <CardAction>
              <Icon className="size-4 text-muted-foreground" />
            </CardAction>
          </CardHeader>
          <CardFooter className="text-muted-foreground">{error ? "Không tải được dữ liệu" : detail}</CardFooter>
        </Card>
      ))}
    </section>
  )
}
