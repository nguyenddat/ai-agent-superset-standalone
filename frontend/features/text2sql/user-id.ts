import { useSyncExternalStore } from "react"

// The standalone app has no sign-in. The chat sends this name as `user_id` so the backend can apply the
// person's own knowledge (own_knowledge); it is not verified and this browser simply remembers it.
const KEY = "text2sql-user-id"
const listeners = new Set<() => void>()
let remembered = ""

function read() {
  try {
    return localStorage.getItem(KEY) ?? ""
  } catch {
    return ""
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useChatUserId() {
  const userId = useSyncExternalStore(subscribe, read, () => "")
  const setUserId = (value: string) => {
    try {
      localStorage.setItem(KEY, value)
    } catch {
      // Private windows can refuse storage; the name then lasts until the page reloads.
    }
    remembered = value
    listeners.forEach((listener) => listener())
  }
  return [userId || remembered, setUserId] as const
}
