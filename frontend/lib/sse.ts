export type ServerSentEvent = { event: string; data: string }

export async function* readServerSentEvents(response: Response): AsyncGenerator<ServerSentEvent> {
  if (!response.body) return
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ""
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value.replaceAll("\r\n", "\n")
    let boundary = buffer.indexOf("\n\n")
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf("\n\n")
      let event = "message"
      const data: string[] = []
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim()
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart())
      }
      if (data.length) yield { event, data: data.join("\n") }
    }
  }
}
