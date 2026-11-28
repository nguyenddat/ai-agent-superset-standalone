// Server-only: the browser calls /api/v1/* on this app; the service key is added here and never sent to it.
export const BACKEND_URL = process.env.API_URL || "http://localhost:8000"

const PASSED_BACK = ["Content-Type", "Cache-Control", "X-Accel-Buffering", "Content-Disposition"]

function json(detail: string, status: number): Response {
  return Response.json({ detail }, { status })
}

// Null when the path leaves /api/v1 or targets own-knowledge, which has its own proxy and keys.
export function proxyTarget(path: string[], search: string, backendUrl = BACKEND_URL): URL | null {
  const url = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}${search}`, backendUrl)
  if (!url.pathname.startsWith("/api/v1/") || url.pathname.startsWith("/api/v1/own-knowledge")) return null
  return url
}

export async function forward(
  request: Request,
  path: string[],
  key = process.env.TEXT2SQL_SERVICE_KEY,
  backendUrl = BACKEND_URL,
): Promise<Response> {
  const target = proxyTarget(path, new URL(request.url).search, backendUrl)
  if (!target) return json("Không tìm thấy.", 404)
  if (!key) return json("Frontend chưa được cấu hình TEXT2SQL_SERVICE_KEY.", 503)

  const headers: Record<string, string> = { "X-Service-Key": key }
  const contentType = request.headers.get("Content-Type")
  if (contentType) headers["Content-Type"] = contentType
  let upstream: Response
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      signal: request.signal, // a closed tab cancels the backend stream too
      cache: "no-store",
    })
  } catch {
    if (request.signal.aborted) return new Response(null, { status: 499 })
    return json("Frontend không kết nối được tới backend.", 502)
  }
  const back = new Headers()
  for (const name of PASSED_BACK) {
    const value = upstream.headers.get(name)
    if (value) back.set(name, value)
  }
  return new Response(upstream.body, { status: upstream.status, headers: back })
}
