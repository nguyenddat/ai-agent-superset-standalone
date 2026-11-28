import assert from "node:assert/strict"
import { createServer, type IncomingMessage } from "node:http"
import type { AddressInfo } from "node:net"
import { after, before, test } from "node:test"

import { forward, proxyTarget } from "./backend-proxy.ts"

const KEY = "proxy-test-key"
let backend = ""
let seen: { url?: string; headers?: IncomingMessage["headers"]; body?: string } = {}
const server = createServer((request, response) => {
  let body = ""
  request.on("data", (chunk) => (body += chunk))
  request.on("end", () => {
    seen = { url: request.url, headers: request.headers, body }
    if (request.url?.startsWith("/api/v1/text2sql/chat/stream")) {
      response.writeHead(200, { "Content-Type": "text/event-stream", "X-Accel-Buffering": "no", "Set-Cookie": "x=1" })
      response.write("event: step\ndata: 1\n\n")
      setTimeout(() => response.end("event: done\ndata: 2\n\n"), 20)
      return
    }
    response.writeHead(201, { "Content-Type": "application/json" })
    response.end('{"ok":true}')
  })
})

before(async () => {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve))
  backend = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
})
after(() => server.close())

test("only /api/v1 paths outside own-knowledge get a target", () => {
  assert.equal(proxyTarget(["metrics", "a b"], "?x=1", "http://b")?.href, "http://b/api/v1/metrics/a%20b?x=1")
  assert.equal(proxyTarget(["own-knowledge", "admin", "entries"], "", "http://b"), null)
  assert.equal(proxyTarget(["x", "..", "own-knowledge", "agent"], "", "http://b"), null)
  assert.equal(proxyTarget(["..", "..", "openapi.json"], "", "http://b"), null)
  assert.equal(proxyTarget(["a/../../../docs"], "", "http://b")?.pathname, "/api/v1/a%2F..%2F..%2F..%2Fdocs")
})

test("adds the key, forwards the body and keeps only safe response headers", async () => {
  const request = new Request("http://app/api/v1/metrics?page=2", {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: "session=1", "X-Service-Key": "from-browser" },
    body: '{"name":"kwh"}',
  })
  const response = await forward(request, ["metrics"], KEY, backend)
  assert.equal(response.status, 201)
  assert.deepEqual(await response.json(), { ok: true })
  assert.equal(seen.url, "/api/v1/metrics?page=2")
  assert.equal(seen.headers?.["x-service-key"], KEY)
  assert.equal(seen.headers?.cookie, undefined)
  assert.equal(seen.body, '{"name":"kwh"}')
})

test("streams server-sent events as they arrive", async () => {
  const request = new Request("http://app/api/v1/text2sql/chat/stream", { method: "POST", body: "{}" })
  const response = await forward(request, ["text2sql", "chat", "stream"], KEY, backend)
  assert.equal(response.headers.get("Content-Type"), "text/event-stream")
  assert.equal(response.headers.get("X-Accel-Buffering"), "no")
  assert.equal(response.headers.get("Set-Cookie"), null)
  const reader = response.body!.getReader()
  const first = new TextDecoder().decode((await reader.read()).value)
  assert.equal(first, "event: step\ndata: 1\n\n") // arrives before the backend ends the response
  let rest = ""
  for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) rest += new TextDecoder().decode(chunk.value)
  assert.equal(rest, "event: done\ndata: 2\n\n")
})

test("fails closed without a key and refuses own-knowledge", async () => {
  const get = new Request("http://app/api/v1/metrics")
  assert.equal((await forward(get, ["metrics"], undefined, backend)).status, 503)
  assert.equal((await forward(get, ["metrics"], "", backend)).status, 503)
  assert.equal((await forward(get, ["own-knowledge", "agent", "entries"], KEY, backend)).status, 404)
})

test("answers 502 when the backend is down", async () => {
  const response = await forward(new Request("http://app/api/v1/metrics"), ["metrics"], KEY, "http://127.0.0.1:1")
  assert.equal(response.status, 502)
})
