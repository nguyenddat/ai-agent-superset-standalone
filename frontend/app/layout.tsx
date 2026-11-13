import type { Metadata } from "next"
import { Geist } from "next/font/google"
import { ThemeProvider } from "next-themes"

import { AppShell } from "@/components/layout/app-shell"
import { Toaster } from "@/components/ui/sonner"
import { cn } from "@/lib/utils"

import "./globals.css"

const geist = Geist({ subsets: ["latin", "latin-ext"], variable: "--font-sans" })

export const metadata: Metadata = {
  title: { default: "AI Agent Superset", template: "%s | AI Agent Superset" },
  description: "Quản lý kết nối database và metadata cho AI Agent Superset Standalone.",
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className={cn("font-sans", geist.variable)} suppressHydrationWarning>
      <body className="min-h-screen antialiased">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} storageKey="theme" disableTransitionOnChange>
          <AppShell>{children}</AppShell>
          <Toaster richColors />
        </ThemeProvider>
      </body>
    </html>
  )
}
