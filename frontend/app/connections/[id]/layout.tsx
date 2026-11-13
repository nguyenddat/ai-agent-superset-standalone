import { Suspense } from "react"

import { ConnectionLayout } from "@/features/database-connections/detail/connection-layout"

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense>
      <ConnectionLayout>{children}</ConnectionLayout>
    </Suspense>
  )
}
