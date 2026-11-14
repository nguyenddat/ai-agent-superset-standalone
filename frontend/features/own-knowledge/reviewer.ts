import { useSyncExternalStore } from "react"

// The standalone app has no sign-in, so the reviewer types a name once and this browser remembers it.
// The backend records it as given; it is a label for the audit trail, not proof of who clicked.
const KEY = "own-knowledge-reviewer"
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

export function useReviewer() {
  const reviewer = useSyncExternalStore(subscribe, read, () => "")
  const setReviewer = (value: string) => {
    try {
      localStorage.setItem(KEY, value)
    } catch {
      // Private windows can refuse storage; the name then lasts until the page reloads.
    }
    remembered = value
    listeners.forEach((listener) => listener())
  }
  return [reviewer || remembered, setReviewer] as const
}
