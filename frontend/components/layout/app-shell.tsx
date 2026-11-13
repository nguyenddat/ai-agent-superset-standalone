import { SiteHeader } from "@/components/layout/site-header"

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6">{children}</main>
    </div>
  )
}
