import { createRequire } from "node:module"
import { pathToFileURL } from "node:url"
const require = createRequire("E:/hede/frontend/package.json")
const viteRequire = createRequire(require.resolve("vitest/node"))
const { createServer } = await import(pathToFileURL(viteRequire.resolve("vite")))
const previewModule = "/__date-calendar-preview.tsx"
const previewSource = `
import React, { useState } from "react"
import { createRoot } from "react-dom/client"
import { DatePicker } from "/components/ui/date-picker"
import { DateRangeControl } from "/components/ui/date-range-control"
import "/app/globals.css"
function Preview() {
  const [date, setDate] = useState("2026-10-16")
  const [start, setStart] = useState("2026-10-01")
  const [end, setEnd] = useState("2026-10-16")
  return <main className="min-h-screen bg-background p-8 text-foreground"><section className="mx-auto max-w-3xl space-y-8 rounded-2xl border bg-card p-6 shadow-sm"><header className="space-y-1"><h1 className="text-lg font-semibold">日期选择</h1><p className="text-sm text-muted-foreground">统一日历样式 · 中文年月 · 日期范围限制</p></header><div className="max-w-xs space-y-2"><label htmlFor="preview-date" className="text-xs font-medium text-muted-foreground">业务日期</label><DatePicker id="preview-date" aria-label="业务日期" value={date} onValueChange={setDate} max="2026-10-31" /></div><DateRangeControl start={start} end={end} onStartChange={setStart} onEndChange={setEnd} maxDate="2026-10-31" /><button type="button" className="rounded-lg border px-3 py-2 text-xs" onClick={() => document.documentElement.classList.toggle("dark")}>切换深色</button></section></main>
}
createRoot(document.getElementById("root")).render(<Preview />)
`
const server = await createServer({
  root: "E:/hede/frontend",
  configFile: false,
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": "E:/hede/frontend" } },
  server: { host: "127.0.0.1", port: 4317, strictPort: true },
  plugins: [{
    name: "date-calendar-preview",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url !== "/" && request.url !== "/index.html") return next()
        response.setHeader("Content-Type", "text/html; charset=utf-8")
        response.end('<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module" src="' + previewModule + '"></script></body></html>')
      })
    },
    resolveId(id) { if (id === previewModule) return "\0date-calendar-preview.tsx" },
    load(id) { if (id === "\0date-calendar-preview.tsx") return previewSource }
  }]
})
await server.listen()
console.log("Date calendar preview: http://127.0.0.1:4317")
process.on("SIGTERM", async () => { await server.close(); process.exit(0) })
