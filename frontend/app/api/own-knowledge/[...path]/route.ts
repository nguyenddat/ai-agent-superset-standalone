import { NextResponse, type NextRequest } from "next/server"
import { timingSafeEqual } from "node:crypto"

import { BACKEND_URL } from "@/lib/backend-proxy"

// The admin key never reaches the browser: this route adds it on the server and forwards only the review routes.
const ALLOWED = /^admin\/entries(\/[0-9a-f-]{36}(\/(review|promote))?)?$/

type Context = { params: Promise<{ path: string[] }> }

async function forward(request: NextRequest, { params }: Context) {
  const path = (await params).path.join("/")
  if (!ALLOWED.test(path)) return NextResponse.json({ detail: "Không tìm thấy." }, { status: 404 })

  const key = process.env.OWN_KNOWLEDGE_ADMIN_KEY
  const password = process.env.OWN_KNOWLEDGE_REVIEW_PASSWORD
  if (!key || !password || password.length < 32) {
    return NextResponse.json(
      { detail: "Frontend chưa được cấu hình khóa admin và mật khẩu duyệt tri thức riêng." },
      { status: 503 },
    )
  }
  const supplied = request.headers.get("X-Review-Password") ?? ""
  const expectedBytes = Buffer.from(password)
  const suppliedBytes = Buffer.from(supplied)
  if (suppliedBytes.length !== expectedBytes.length || !timingSafeEqual(suppliedBytes, expectedBytes)) {
    return NextResponse.json({ detail: "Mật khẩu duyệt không đúng." }, { status: 401 })
  }

  let response: Response
  try {
    response = await fetch(`${BACKEND_URL}/api/v1/own-knowledge/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers: { "Content-Type": "application/json", "X-Own-Knowledge-Key": key },
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
    })
  } catch {
    return NextResponse.json({ detail: "Frontend không kết nối được tới backend." }, { status: 502 })
  }
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  })
}

export const GET = forward
export const POST = forward
