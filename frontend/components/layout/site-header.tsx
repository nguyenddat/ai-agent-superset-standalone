"use client"

import Link from "next/link"
import { DatabaseZapIcon, MoonIcon, SunIcon } from "lucide-react"
import { useTheme } from "next-themes"

import { Button } from "@/components/ui/button"

export function SiteHeader() {
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <header className="sticky top-0 z-50 flex h-14 w-full items-center gap-2 border-b bg-background px-4">
      <Link href="/" className="flex items-center gap-2 text-base font-semibold">
        <DatabaseZapIcon className="size-5" />
        AI Agent Superset
      </Link>
      <Button
        variant="ghost"
        size="icon"
        className="ml-auto"
        aria-label="Đổi giao diện sáng/tối"
        onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      >
        <SunIcon className="hidden dark:block" />
        <MoonIcon className="dark:hidden" />
      </Button>
    </header>
  )
}
