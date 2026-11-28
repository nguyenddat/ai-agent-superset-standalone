// Same origin: app/api/v1/[...path] forwards to the backend and adds the service key on the server.
export const API_URL = ""

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

export function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  return requestJson<T>(`${API_URL}${path}`, init)
}

// For routes this app serves itself, such as the server-side proxy that holds a secret key.
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
    })
  } catch {
    throw new ApiError(0, "Không kết nối được tới backend. Kiểm tra server API đã chạy chưa.")
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body?.detail ?? "Đã xảy ra lỗi khi gọi API.")
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
