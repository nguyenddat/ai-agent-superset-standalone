export type ConnectionParts = {
  host: string
  port: string
  database: string
  username: string
  password: string
}

export function buildConnectionUri(
  dialect: string,
  driver: string,
  parts: ConnectionParts,
): string | null {
  const host = parts.host.trim()
  const database = parts.database.trim()
  const username = parts.username.trim()
  const portText = parts.port.trim()
  const port = Number(portText)
  const validHost = /^[a-zA-Z0-9._-]+$/.test(host) || /^\[[0-9a-fA-F:]+\]$/.test(host)

  if (!validHost || !database || !username || !/^\d+$/.test(portText) || port < 1 || port > 65535) {
    return null
  }

  return `${dialect}+${driver}://${encodeURIComponent(username)}:${encodeURIComponent(parts.password)}@${host}:${port}/${encodeURIComponent(database)}`
}
