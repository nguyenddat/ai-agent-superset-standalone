import type { NextRequest } from "next/server"

import { forward } from "@/lib/backend-proxy"

type Context = { params: Promise<{ path: string[] }> }

async function handle(request: NextRequest, { params }: Context) {
  return forward(request, (await params).path)
}

export const GET = handle
export const POST = handle
export const PUT = handle
export const PATCH = handle
export const DELETE = handle
