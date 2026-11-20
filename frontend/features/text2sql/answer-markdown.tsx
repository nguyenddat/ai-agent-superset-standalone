"use client"

import { memo } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

// The agent answers in short Markdown: paragraphs, bold figures, lists and small tables.
const components: Components = {
  p: ({ children }) => <p className="leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="ml-5 flex list-disc flex-col gap-1">{children}</ul>,
  ol: ({ children }) => <ol className="ml-5 flex list-decimal flex-col gap-1">{children}</ol>,
  h1: ({ children }) => <h3 className="font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="font-semibold">{children}</h3>,
  h3: ({ children }) => <h3 className="font-semibold">{children}</h3>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-3">
      {children}
    </a>
  ),
  code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">{children}</code>,
  table: ({ children }) => (
    <div className="w-fit max-w-full rounded-lg border">
      <Table>{children}</Table>
    </div>
  ),
  thead: ({ children }) => <TableHeader>{children}</TableHeader>,
  tbody: ({ children }) => <TableBody>{children}</TableBody>,
  tr: ({ children }) => <TableRow>{children}</TableRow>,
  th: ({ children, style }) => <TableHead style={style}>{children}</TableHead>,
  td: ({ children, style }) => <TableCell style={style}>{children}</TableCell>,
}

const Block = memo(function Block({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {text}
    </ReactMarkdown>
  )
})

// Text that is still arriving can end mid-way through Markdown: a half table row is held back until its line ends,
// and an unclosed ** or ` in the last block is closed for now so the rest does not flash as raw syntax.
export function closeOpenMarkdown(text: string): string {
  const lines = text.split("\n")
  if (lines.length && lines.at(-1)!.trimStart().startsWith("|")) lines.pop()
  let tail = lines.join("\n")
  if ((tail.match(/```/g) ?? []).length % 2 === 1) return `${tail}\n\`\`\``
  const inline = tail.replace(/```[\s\S]*?```/g, "")
  if ((inline.match(/`/g) ?? []).length % 2 === 1) tail += "`"
  if ((inline.match(/\*\*/g) ?? []).length % 2 === 1) tail = `${tail.replace(/\s+$/, "")}**`
  return tail
}

// Finished blocks (split at blank lines) render once; only the block still growing re-renders as text arrives.
export function AnswerMarkdown({ text, streaming = false }: { text: string; streaming?: boolean }) {
  if (!streaming) return <Block text={text} />
  const blocks = text.split(/\n{2,}/)
  const last = blocks.length - 1
  return (
    <>
      {blocks.map((block, index) => (
        <Block key={index} text={index === last ? closeOpenMarkdown(block) : block} />
      ))}
    </>
  )
}
