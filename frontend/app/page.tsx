import { ConnectionsView } from "@/features/database-connections/connections-view"

export default function HomePage() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 sm:px-2">
      <ConnectionsView />
    </div>
  )
}
