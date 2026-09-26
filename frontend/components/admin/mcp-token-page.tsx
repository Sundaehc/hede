"use client"

import Link from "next/link"
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import {
  ArrowLeft,
  Ban,
  Check,
  ChevronDown,
  Copy,
  Eye,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
} from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { McpAccountPicker } from "@/components/admin/mcp-account-picker"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import {
  issueMcpToken,
  listMcpTokenAudit,
  listMcpTokens,
  revokeMcpToken,
  type IssuedMcpToken,
  type McpAuditItem,
  type McpAuditPage,
  type McpCandidate,
  type McpPage,
  type McpProfile,
  type McpTokenItem,
} from "@/lib/mcp-tokens"
import { cn } from "@/lib/utils"
import { copyTextareaText, selectTextareaText } from "@/lib/copy-textarea"

const PROFILE_NAMES: Record<McpProfile, string> = { products: "商品档案（历史凭证）", design: "商品档案 + 美工文案", finance: "财务部数据", merchandise: "商品部数据", operation: "运营部数据", development: "开发部数据", customer_service: "客服部数据" }
const STATES = {
  active: {
    name: "有效",
    tone: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  revoked: { name: "已撤销", tone: "bg-muted text-muted-foreground" },
  expired: {
    name: "已到期",
    tone: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  blocked: {
    name: "账号权限失效",
    tone: "bg-rose-500/10 text-rose-700 dark:text-rose-400",
  },
}

function dateLabel(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
  })
}

function messageOf(error: unknown) {
  return error instanceof Error
    ? error.message
    : "操作失败，请刷新确认状态后重试"
}

const AUDIT_STATUS_NAMES: Record<string, string> = { started: "\u6267\u884c\u4e2d", completed: "\u6210\u529f", rejected: "\u5df2\u62d2\u7edd", failed: "\u5931\u8d25" }
const TOOL_NAMES: Record<string, string> = { list_datasets: "\u67e5\u770b\u6570\u636e\u96c6", describe_dataset: "\u67e5\u770b\u5b57\u6bb5\u8bf4\u660e", query_readonly: "\u53ea\u8bfb\u67e5\u8be2" }

function AuditDetail({ item }: { item: McpAuditItem }) {
  const summary = item.result_summary
  return (
    <details className="group rounded-lg border border-border bg-muted/20">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-medium [&::-webkit-details-marker]:hidden">
        <span>{"\u67e5\u770b\u67e5\u8be2\u660e\u7ec6"}</span><ChevronDown className="size-4 transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-3 border-t border-border p-3 text-xs">
        {item.datasets.length ? <div><p className="mb-1 font-medium text-muted-foreground">{"\u6570\u636e\u96c6"}</p><div className="flex flex-wrap gap-1.5">{item.datasets.map((dataset) => <span key={dataset} className="rounded bg-background px-2 py-1 font-mono">{dataset}</span>)}</div></div> : null}
        {item.query_sql ? <div><p className="mb-1 font-medium text-muted-foreground">SQL</p><pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-background p-2 font-mono leading-5">{item.query_sql}</pre></div> : null}
        {item.query_params ? <div><p className="mb-1 font-medium text-muted-foreground">{"\u67e5\u8be2\u53c2\u6570"}</p><pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-background p-2 font-mono leading-5">{JSON.stringify(item.query_params, null, 2)}</pre></div> : null}
        {summary ? <div><p className="mb-1 font-medium text-muted-foreground">{"\u7ed3\u679c\u6458\u8981"}</p><div className="overflow-x-auto rounded bg-background"><table className="min-w-full text-left font-mono text-[11px]"><thead className="border-b border-border"><tr>{summary.columns.map((column) => <th key={column} className="px-2 py-1.5 font-medium">{column}</th>)}</tr></thead><tbody>{summary.rows.map((row, rowIndex) => <tr key={rowIndex} className="border-b border-border last:border-0">{summary.columns.map((column, columnIndex) => <td key={`${rowIndex}-${column}`} className="max-w-64 whitespace-pre-wrap break-words px-2 py-1.5 align-top">{String(row[columnIndex] ?? "")}</td>)}</tr>)}</tbody></table></div>{summary.truncated ? <p className="mt-1 text-muted-foreground">{"\u7ed3\u679c\u6458\u8981\u5df2\u622a\u65ad\uff0c\u4ec5\u5c55\u793a\u90e8\u5206\u6807\u8bc6\u3002"}</p> : null}</div> : null}
        {!item.query_sql && !item.query_params && !summary ? <p className="text-muted-foreground">{"\u8be5\u8bb0\u5f55\u4ea7\u751f\u4e8e\u5ba1\u8ba1\u660e\u7ec6\u5347\u7ea7\u524d\uff0c\u6682\u65e0\u5177\u4f53\u67e5\u8be2\u5185\u5bb9\u3002"}</p> : null}
      </div>
    </details>
  )
}

export function McpTokenPage() {
  const { user, loading, hasPermission } = useAuth()
  if (loading)
    return (
      <div className="app-page">
        <p className="app-content text-sm text-muted-foreground" role="status">
          正在确认管理权限…
        </p>
      </div>
    )
  if (
    user?.role_code !== "super_admin" ||
    user.status !== "active" ||
    !hasPermission("system.admin")
  ) {
    return (
      <div className="app-page">
        <div className="app-content">
          <div className="surface-panel p-8 text-sm text-muted-foreground">
            仅超级管理员可以管理 MCP Token。
          </div>
        </div>
      </div>
    )
  }
  return <TokenManager key={user.id} />
}

function TokenManager() {
  const [result, setResult] = useState<McpPage<McpTokenItem> | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<McpCandidate | null>(null)
  const [profile, setProfile] = useState<McpProfile>("products")
  const [days, setDays] = useState("30")
  const [permanent, setPermanent] = useState(false)
  const [label, setLabel] = useState("")
  const [saving, setSaving] = useState(false)
  const [mutationError, setMutationError] = useState("")
  const [issued, setIssued] = useState<IssuedMcpToken | null>(null)
  const [copied, setCopied] = useState(false)
  const [copying, setCopying] = useState(false)
  const [copyError, setCopyError] = useState("")
  const tokenTextarea = useRef<HTMLTextAreaElement>(null)
  const copyingTextarea = useRef<HTMLTextAreaElement | null>(null)
  const [revokeTarget, setRevokeTarget] = useState<McpTokenItem | null>(null)
  const [auditTarget, setAuditTarget] = useState<McpTokenItem | null>(null)
  const [auditResult, setAuditResult] = useState<McpAuditPage | null>(null)
  const [auditPage, setAuditPage] = useState(1)
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState("")
  const mounted = useRef(true)
  const busy = useRef(false)
  const listSequence = useRef(0)
  const auditSequence = useRef(0)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const load = useCallback(() => {
    const sequence = ++listSequence.current
    return listMcpTokens(page)
      .then((response) => {
        if (mounted.current && sequence === listSequence.current) {
          setResult(response)
          setError("")
        }
      })
      .catch((failure: unknown) => {
        if (mounted.current && sequence === listSequence.current)
          setError(messageOf(failure))
      })
      .finally(() => {
        if (mounted.current && sequence === listSequence.current)
          setLoading(false)
      })
  }, [page])

  useEffect(() => {
    void load()
  }, [load])

  const loadAudit = useCallback(() => {
    if (!auditTarget) return Promise.resolve()
    const sequence = ++auditSequence.current
    return listMcpTokenAudit(auditTarget.id, auditPage).then((response) => {
      if (mounted.current && sequence === auditSequence.current) { setAuditResult(response); setAuditError("") }
    }).catch((failure: unknown) => {
      if (mounted.current && sequence === auditSequence.current) setAuditError(messageOf(failure))
    }).finally(() => {
      if (mounted.current && sequence === auditSequence.current) setAuditLoading(false)
    })
  }, [auditPage, auditTarget])

  useEffect(() => { if (auditTarget) void loadAudit() }, [auditTarget, loadAudit])

  function refreshList() {
    setLoading(true)
    void load()
  }

  function changePage(next: number) {
    setLoading(true)
    setPage(next)
  }

  function openAudit(item: McpTokenItem) {
    setAuditTarget(item); setAuditResult(null); setAuditPage(1); setAuditLoading(true); setAuditError("")
  }

  function closeAudit() {
    setAuditTarget(null); setAuditResult(null); setAuditError("")
  }

  function openCreate() {
    setSelectedUser(null)
    setProfile("design")
    setDays("30")
    setPermanent(false)
    setLabel("")
    setMutationError("")
    setNotice("")
    setCreateOpen(true)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy.current || !selectedUser || !selectedUser.profiles.includes(profile)) return
    const lifetime = Number(days)
    if (
      (!permanent &&
        (!Number.isInteger(lifetime) || lifetime < 1 || lifetime > 90)) ||
      !label.trim()
    ) {
      setMutationError("请填写用途备注，并选择永久有效或 1～90 天的有效期")
      return
    }
    busy.current = true
    setSaving(true)
    setMutationError("")
    try {
      const response = await issueMcpToken({
        user_id: selectedUser.id,
        profile,
        days: permanent ? null : lifetime,
        label: label.trim(),
      })
      if (!mounted.current) return
      setIssued(response)
      setCopied(false)
      setCopying(false)
      setCopyError("")
      setCreateOpen(false)
      if (page === 1) refreshList()
      else changePage(1)
    } catch (failure) {
      if (mounted.current)
        setMutationError(
          `${messageOf(failure)}。若连接中断，请先刷新凭证列表确认是否已签发，避免重复创建。`
        )
    } finally {
      busy.current = false
      if (mounted.current) setSaving(false)
    }
  }

  async function confirmRevoke() {
    if (busy.current || !revokeTarget) return
    busy.current = true
    setSaving(true)
    setMutationError("")
    try {
      await revokeMcpToken(revokeTarget.id)
      if (!mounted.current) return
      setRevokeTarget(null)
      setNotice("凭证已撤销，后续请求将被拒绝。")
      refreshList()
    } catch (failure) {
      if (mounted.current) setMutationError(messageOf(failure))
    } finally {
      busy.current = false
      if (mounted.current) setSaving(false)
    }
  }

  async function copyToken() {
    const textarea = tokenTextarea.current
    if (!issued || !textarea || copyingTextarea.current === textarea) return
    copyingTextarea.current = textarea
    setCopying(true)
    setCopied(false)
    setCopyError("")
    try {
      const success = await copyTextareaText(textarea)
      if (!mounted.current || tokenTextarea.current !== textarea) return
      setCopied(success)
      setCopyError(success ? "" : "未能自动复制。请点击“全选 Token”后按 Ctrl+C（Mac：⌘C），或长按选区手动复制。")
    } finally {
      if (copyingTextarea.current === textarea) copyingTextarea.current = null
      if (mounted.current && tokenTextarea.current === textarea) setCopying(false)
    }
  }

  function closeIssued() {
    setIssued(null)
    setCopied(false)
    setCopying(false)
    setCopyError("")
  }

  const totalPages = Math.max(1, Math.ceil((result?.total ?? 0) / 20))
  return (
    <div className="app-page">
      <div className="app-content space-y-5">
        <div className="page-header">
          <div>
            <Link
              href="/admin"
              className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="size-3.5" />
              用户管理
            </Link>
            <h1 className="page-title">MCP Token 管理</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={refreshList} disabled={loading}>
              <RefreshCw className={cn("size-4", loading && "animate-spin")} />
              刷新
            </Button>
            <Button
              onClick={openCreate}
              disabled={saving || loading || !!error}
            >
              <Plus className="size-4" />
              签发 Token
            </Button>
          </div>
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-destructive/25 bg-destructive/5 p-4 text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}
        {notice ? (
          <p
            role="status"
            className="text-sm text-emerald-700 dark:text-emerald-400"
          >
            {notice}
          </p>
        ) : null}
        <section
          className="surface-panel overflow-hidden"
          aria-label="已签发凭证"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold">
              凭证记录{" "}
              <span className="ml-2 font-mono text-muted-foreground">
                {result?.total ?? "—"}
              </span>
            </h2>
          </div>
          <div className="overflow-x-auto" aria-busy={loading}>
            <table className="w-full min-w-[800px] text-left text-sm">
              <thead className="bg-muted/40 text-xs text-muted-foreground">
                <tr>
                  {[
                    "账号 / 部门",
                    "用途备注",
                    "查询范围",
                    "状态",
                    "签发 / 到期时间",
                    "操作",
                  ].map((heading) => (
                    <th key={heading} className="px-5 py-3 font-medium">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {loading ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="p-10 text-center text-muted-foreground"
                    >
                      正在加载凭证…
                    </td>
                  </tr>
                ) : error ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="p-10 text-center text-muted-foreground"
                    >
                      加载失败，请刷新重试。
                    </td>
                  </tr>
                ) : result?.items.length ? (
                  result.items.map((item) => (
                    <tr key={item.id} className="hover:bg-muted/20">
                      <td className="px-5 py-4">
                        <p className="font-medium">{item.username}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {item.display_name} · {item.department_code}
                        </p>
                      </td>
                      <td className="max-w-60 px-5 py-4">
                        <p className="break-words">{item.label}</p>
                        <p className="mt-1 font-mono text-xs text-muted-foreground">
                          #{item.id}
                        </p>
                      </td>
                      <td className="px-5 py-4 text-xs">
                        {PROFILE_NAMES[item.profile]}
                      </td>
                      <td className="px-5 py-4">
                        <span
                          className={cn(
                            "inline-flex rounded-full px-2.5 py-1 text-xs",
                            STATES[item.state].tone
                          )}
                        >
                          {STATES[item.state].name}
                        </span>
                      </td>
                      <td className="px-5 py-4 font-mono text-xs leading-6">
                        <p className="text-muted-foreground">
                          {dateLabel(item.created_at)}
                        </p>
                        <p>
                          {item.expires_at === null
                            ? "永久有效"
                            : dateLabel(item.expires_at)}
                        </p>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap gap-2">
                        <Button variant="outline" size="sm" disabled={saving} aria-label={`查询 ${item.label} 的记录`} onClick={() => openAudit(item)}>
                          <Eye className="size-3.5" />
                          {"\u67e5\u8be2\u8bb0\u5f55"}
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={item.state === "revoked" || saving}
                          aria-label={`撤销 ${item.label}`}
                          onClick={() => {
                            setMutationError("")
                            setRevokeTarget(item)
                          }}
                        >
                          <Ban className="size-3.5" />
                          撤销
                        </Button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="p-12 text-center">
                      <KeyRound className="mx-auto mb-3 size-6 text-muted-foreground" />
                      <p className="font-medium">还没有签发凭证</p>
                      <p className="mt-2 text-xs text-muted-foreground">
                        点击“签发 Token”，为一个中台账号开通查询。
                      </p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-border px-5 py-3 text-xs text-muted-foreground">
            <span>
              第 {page} / {totalPages} 页
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || loading}
                onClick={() => changePage(page - 1)}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => changePage(page + 1)}
              >
                下一页
              </Button>
            </div>
          </div>
        </section>

        <Dialog
          open={createOpen}
          onOpenChange={(open) => {
            if (!busy.current) setCreateOpen(open)
          }}
        >
          <DialogContent className="max-h-[90dvh] max-w-xl overflow-y-auto">
            <DialogHeader>
              <DialogTitle>签发个人 Token</DialogTitle>
              <DialogDescription>
                选择商品运营中台的登录账号。只有启用且有商品查看权限的账号会出现在这里。
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={submit} className="mt-5 space-y-4">
              <McpAccountPicker
                value={selectedUser}
                disabled={saving}
                onChange={(candidate) => {
                  setSelectedUser(candidate)
                  setProfile(candidate.profiles[0])
                }}
              />
              <div className="grid gap-4 sm:grid-cols-[1fr_130px]">
                <div className="space-y-2">
                  <label htmlFor="mcp-profile" className="text-sm font-medium">
                    查询范围
                  </label>
                  <Select
                    id="mcp-profile"
                    value={profile}
                    disabled={saving || !selectedUser}
                    onChange={(event) =>
                      setProfile(event.target.value as McpProfile)
                    }
                  >
                    {!selectedUser?.profiles.length ? (
                      <option value="">该账号无可用查询范围</option>
                    ) : null}
                    {selectedUser?.profiles.map((item) => (
                      <option key={item} value={item}>{PROFILE_NAMES[item]}</option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <label htmlFor="mcp-days" className="text-sm font-medium">
                    有效期（天）
                  </label>
                  <Input
                    id="mcp-days"
                    type="number"
                    min={1}
                    max={90}
                    step={1}
                    required
                    value={days}
                    disabled={saving || permanent}
                    onChange={(event) => setDays(event.target.value)}
                  />
                </div>
              </div>
              <label
                htmlFor="mcp-permanent"
                className="flex items-start gap-3 rounded-lg border p-3 text-sm"
              >
                <input
                  id="mcp-permanent"
                  type="checkbox"
                  className="mt-1 size-4 accent-primary"
                  checked={permanent}
                  disabled={saving}
                  onChange={(event) => setPermanent(event.target.checked)}
                  aria-describedby="mcp-permanent-description"
                />
                <span>
                  <span className="font-medium">永久有效</span>
                  <span
                    id="mcp-permanent-description"
                    className="mt-1 block text-xs leading-5 text-muted-foreground"
                  >
                    不会自动到期，仍可手动撤销；账号停用或失去对应权限后不可使用。
                  </span>
                </span>
              </label>
              <div className="space-y-2">
                <label htmlFor="mcp-label" className="text-sm font-medium">
                  用途备注
                </label>
                <Input
                  id="mcp-label"
                  placeholder="例如：张三 · 办公电脑 Codex"
                  maxLength={100}
                  required
                  value={label}
                  disabled={saving}
                  onChange={(event) => setLabel(event.target.value)}
                />
              </div>
              {mutationError ? (
                <p role="alert" className="text-sm text-destructive">
                  {mutationError}
                </p>
              ) : null}
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  disabled={saving}
                  onClick={() => setCreateOpen(false)}
                >
                  取消
                </Button>
                <Button
                  type="submit"
                  disabled={saving || !selectedUser?.profiles.includes(profile) || !label.trim()}
                >
                  {saving ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <KeyRound className="size-4" />
                  )}
                  确认签发
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        <Dialog
          open={issued !== null}
          onOpenChange={(open) => {
            if (!open) closeIssued()
          }}
        >
          <DialogContent aria-labelledby={undefined} aria-label={"Token \u5df2\u7b7e\u53d1\uff0c\u8bf7\u7acb\u5373\u4fdd\u5b58"}>
            <DialogHeader>
              <DialogTitle>Token 已签发，请立即保存</DialogTitle>
              <DialogDescription>
                关闭后无法再次查看明文。请通过安全渠道交付给本人，不要发送到群聊或提交代码仓库。
              </DialogDescription>
            </DialogHeader>
            {issued ? (
              <div className="mt-5 space-y-4">
                <div className="flex items-center justify-between text-sm">
                  <span>
                    {issued.item.username} · #{issued.item.id}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {PROFILE_NAMES[issued.item.profile]}
                  </span>
                </div>
                <label htmlFor="mcp-secret" className="sr-only">
                  新签发的 Token
                </label>
                <textarea
                  id="mcp-secret"
                  ref={tokenTextarea}
                  readOnly
                  autoComplete="off"
                  spellCheck={false}
                  value={issued.token}
                  aria-describedby={copyError ? "mcp-copy-error" : undefined}
                  onFocus={(event) => event.target.select()}
                  className="min-h-28 w-full resize-none rounded-lg border border-border bg-muted p-4 font-mono text-sm break-all select-text focus-visible:outline-2 focus-visible:outline-ring"
                />
                <p className="text-xs text-muted-foreground">
                  到期时间：
                  {issued.item.expires_at === null
                    ? "永久有效"
                    : `${dateLabel(issued.item.expires_at)}（北京时间）`}
                </p>
                {copyError ? (
                  <p id="mcp-copy-error" role="alert" className="text-xs text-destructive">
                    {copyError}
                  </p>
                ) : null}
                <DialogFooter>
                  <Button variant="outline" onClick={closeIssued}>
                    我已保存，关闭
                  </Button>
                  <Button variant="outline" onClick={() => { if (tokenTextarea.current) selectTextareaText(tokenTextarea.current) }}>
                    全选 Token
                  </Button>
                  <Button disabled={copying} onClick={() => void copyToken()}>
                    {copying ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : copied ? (
                      <Check className="size-4" />
                    ) : (
                      <Copy className="size-4" />
                    )}
                    {copying ? "正在复制…" : copied ? "已复制" : "复制 Token"}
                  </Button>
                </DialogFooter>
              </div>
            ) : null}
          </DialogContent>
        </Dialog>

        <Dialog
          open={auditTarget !== null}
          onOpenChange={(open) => {
            if (!open) closeAudit()
          }}
        >
          <DialogContent aria-label={"Token \u67e5\u8be2\u8bb0\u5f55"} className="flex max-h-[90dvh] max-w-5xl flex-col overflow-hidden">
            <DialogHeader>
              <DialogTitle>{"Token \u67e5\u8be2\u8bb0\u5f55"}</DialogTitle>
              <DialogDescription>
                {auditTarget?.username} · {auditTarget?.label} · #{auditTarget?.id}
              </DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-y-auto py-4">
              {auditError ? <p role="alert" className="rounded-lg bg-destructive/5 p-3 text-sm text-destructive">{auditError}</p> : null}
              {!auditError && auditResult && !auditResult.details_available ? <p className="mb-3 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">{"\u5f53\u524d\u6570\u636e\u5e93\u8fd8\u672a\u5347\u7ea7\u67e5\u8be2\u660e\u7ec6\u5b57\u6bb5\uff1b\u5347\u7ea7\u540e\u53ea\u80fd\u8bb0\u5f55\u65b0\u7684\u67e5\u8be2\uff0c\u5386\u53f2\u8bb0\u5f55\u65e0\u6cd5\u8865\u56de\u5177\u4f53\u5185\u5bb9\u3002"}</p> : null}
              {auditLoading ? <p className="p-10 text-center text-sm text-muted-foreground">{"\u6b63\u5728\u52a0\u8f7d\u67e5\u8be2\u8bb0\u5f55\u2026"}</p> : null}
              {!auditLoading && !auditError && auditResult?.items.length === 0 ? <p className="p-10 text-center text-sm text-muted-foreground">{"\u8fd9\u4e2a Token \u8fd8\u6ca1\u6709\u67e5\u8be2\u8bb0\u5f55\u3002"}</p> : null}
              {!auditLoading && !auditError && auditResult?.items.length ? <div className="space-y-3">{auditResult.items.map((item) => <article key={item.request_id} className="rounded-xl border border-border p-3"><div className="flex flex-wrap items-center justify-between gap-2 text-xs"><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{TOOL_NAMES[item.tool] ?? item.tool}</span><span className={cn("rounded-full px-2 py-1", item.status === "completed" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : item.status === "rejected" || item.status === "failed" ? "bg-rose-500/10 text-rose-700 dark:text-rose-400" : "bg-amber-500/10 text-amber-700 dark:text-amber-400")}>{AUDIT_STATUS_NAMES[item.status] ?? item.status}</span>{item.datasets.map((dataset) => <span key={dataset} className="rounded bg-muted px-2 py-1 font-mono">{dataset}</span>)}</div><span className="font-mono text-muted-foreground">{dateLabel(item.created_at)}</span></div><div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground"><span>{"\u8fd4\u56de"} {item.row_count} {"\u884c"}</span><span>{"\u8017\u65f6"} {item.elapsed_ms} ms</span><span className="font-mono">{"\u8bf7\u6c42"} {item.request_id.slice(0, 12)}</span></div><div className="mt-3"><AuditDetail item={item} /></div></article>)}</div> : null}
            </div>
            <DialogFooter className="border-t border-border pt-4">
              <span className="mr-auto text-xs text-muted-foreground">{"\u5171"} {auditResult?.total ?? "—"} {"\u6761"}</span>
              <Button variant="outline" size="sm" disabled={auditPage <= 1 || auditLoading} onClick={() => { setAuditLoading(true); setAuditPage((current) => current - 1) }}>{"\u4e0a\u4e00\u9875"}</Button>
              <Button variant="outline" size="sm" disabled={!auditResult || auditPage >= Math.max(1, Math.ceil((auditResult.total ?? 0) / 20)) || auditLoading} onClick={() => { setAuditLoading(true); setAuditPage((current) => current + 1) }}>{"\u4e0b\u4e00\u9875"}</Button>
              <Button variant="outline" onClick={closeAudit}>{"\u5173\u95ed"}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog
          open={revokeTarget !== null}
          onOpenChange={(open) => {
            if (!open && !busy.current) setRevokeTarget(null)
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>撤销此 Token？</DialogTitle>
              <DialogDescription>
                撤销 {revokeTarget?.username} 的“{revokeTarget?.label}
                ”后不可恢复。后续查询会被拒绝；已经执行中的请求不会立即中断。需要使用时请重新签发。
              </DialogDescription>
            </DialogHeader>
            {mutationError ? (
              <p role="alert" className="mt-4 text-sm text-destructive">
                {mutationError}
              </p>
            ) : null}
            <DialogFooter className="mt-6">
              <Button
                variant="outline"
                disabled={saving}
                onClick={() => setRevokeTarget(null)}
              >
                取消
              </Button>
              <Button
                variant="destructive"
                disabled={saving}
                onClick={() => void confirmRevoke()}
              >
                {saving ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Ban className="size-4" />
                )}
                确认撤销
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
