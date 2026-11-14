import { SiteHeader } from "@/components/layout/site-header"

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <SiteHeader />
      <main className="flex w-full flex-col gap-3 px-3 py-3 sm:px-4">{children}</main>
    </div>
  )
}
