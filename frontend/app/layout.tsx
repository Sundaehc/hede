import type { Metadata } from "next"
import localFont from "next/font/local"

import "./globals.css"
import { AppShell } from "@/components/auth/app-shell"
import { AuthProvider } from "@/components/auth/auth-provider"
import { ThemeProvider } from "@/components/theme-provider"

import { cn } from "@/lib/utils"

const geist = localFont({
  src: "./fonts/geist-latin.woff2",
  display: "swap",
  variable: "--font-sans",
  weight: "100 900",
})

const fontMono = localFont({
  src: "./fonts/geist-mono-latin.woff2",
  display: "swap",
  variable: "--font-mono",
  weight: "100 900",
})

export const metadata: Metadata = {
  title: "赫德",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="zh-CN"
      suppressHydrationWarning
      className={cn("antialiased", fontMono.variable, "font-sans", geist.variable)}
    >
      <body>
        <ThemeProvider>
          <AuthProvider>
            <AppShell>{children}</AppShell>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
