"use client"

import Link from "next/link"
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import {
  ArrowLeft,
  Ban,
  Check,
  Copy,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
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
  listMcpCandidates,
  listMcpTokens,
  revokeMcpToken,
  type IssuedMcpToken,
  type McpCandidate,
  type McpPage,
  type McpProfile,
  type McpTokenItem,
} from "@/lib/mcp-tokens"
import { cn } from "@/lib/utils"

const PROFILE_NAMES = { products: "商品档案", design: "商品档案 + 美工文案" }
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
  const [candidates, setCandidates] = useState<McpPage<McpCandidate> | null>(
    null
  )
  const [candidatePage, setCandidatePage] = useState(1)
  const [searchVersion, setSearchVersion] = useState(0)
  const [search, setSearch] = useState("")
  const [searchDraft, setSearchDraft] = useState("")
  const [candidateLoading, setCandidateLoading] = useState(false)
  const [candidateError, setCandidateError] = useState("")
  const [selectedUser, setSelectedUser] = useState<McpCandidate | null>(null)
  const [profile, setProfile] = useState<McpProfile>("products")
  const [days, setDays] = useState("30")
  const [permanent, setPermanent] = useState(false)
  const [label, setLabel] = useState("")
  const [saving, setSaving] = useState(false)
  const [mutationError, setMutationError] = useState("")
  const [issued, setIssued] = useState<IssuedMcpToken | null>(null)
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState("")
  const [revokeTarget, setRevokeTarget] = useState<McpTokenItem | null>(null)
  const mounted = useRef(true)
  const busy = useRef(false)
  const listSequence = useRef(0)

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

  useEffect(() => {
    if (!createOpen) return
    let cancelled = false
    void listMcpCandidates(search, candidatePage)
      .then((response) => {
        if (!cancelled) setCandidates(response)
      })
      .catch((failure: unknown) => {
        if (!cancelled) setCandidateError(messageOf(failure))
      })
      .finally(() => {
        if (!cancelled) setCandidateLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [createOpen, search, candidatePage, searchVersion])

  function refreshList() {
    setLoading(true)
    void load()
  }

  function changePage(next: number) {
    setLoading(true)
    setPage(next)
  }

  function findCandidates(nextPage = 1) {
    setCandidateLoading(true)
    setCandidateError("")
    setSearch(searchDraft.trim())
    setCandidatePage(nextPage)
    setSearchVersion((version) => version + 1)
  }

  function openCreate() {
    setSelectedUser(null)
    setProfile("products")
    setDays("30")
    setPermanent(false)
    setLabel("")
    setSearch("")
    setSearchDraft("")
    setCandidatePage(1)
    setCandidateLoading(true)
    setCandidateError("")
    setCandidates(null)
    setMutationError("")
    setNotice("")
    setCreateOpen(true)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy.current || !selectedUser) return
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
    if (!issued) return
    try {
      await navigator.clipboard.writeText(issued.token)
      if (mounted.current) {
        setCopied(true)
        setCopyError("")
      }
    } catch {
      if (mounted.current)
        setCopyError(
          "当前浏览器不支持自动复制，请选中文本手动复制；建议使用 HTTPS 访问中台。"
        )
    }
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
            <p className="page-subtitle">
              为中台账号签发个人查询凭证，不共享数据库账号。
            </p>
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

        <section
          className="surface-panel grid overflow-hidden md:grid-cols-[1.1fr_1fr_1fr]"
          aria-label="凭证使用说明"
        >
          <div className="border-b border-border bg-muted/40 p-5 md:border-r md:border-b-0">
            <ShieldCheck className="mb-3 size-5 text-primary" />
            <h2 className="text-sm font-semibold">一人一证，随时撤销</h2>
            <p className="mt-2 text-xs leading-6 text-muted-foreground">
              账号停用或失去相应权限后，新请求自动失效。Token 明文仅签发时展示。
            </p>
          </div>
          <div className="border-b border-border p-5 md:border-r md:border-b-0">
            <p className="text-[11px] font-semibold tracking-widest text-muted-foreground">
              PRODUCTS
            </p>
            <h2 className="mt-2 text-sm font-semibold">商品档案</h2>
            <p className="mt-2 text-xs leading-6 text-muted-foreground">
              开放授权的商品字段，不含成本、供应商及原始数据。
            </p>
          </div>
          <div className="p-5">
            <p className="text-[11px] font-semibold tracking-widest text-muted-foreground">
              DESIGN
            </p>
            <h2 className="mt-2 text-sm font-semibold">商品档案 + 美工文案</h2>
            <p className="mt-2 text-xs leading-6 text-muted-foreground">
              增加当前文案及历史版本，仅美工部、超级管理员可开通。
            </p>
          </div>
        </section>

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
            <p className="text-xs text-muted-foreground">
              时间：北京时间 · 列表不保存或返回明文
            </p>
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
              <div className="space-y-2">
                <label
                  htmlFor="mcp-user-search"
                  className="text-sm font-medium"
                >
                  查找账号
                </label>
                <div className="flex gap-2">
                  <Input
                    id="mcp-user-search"
                    placeholder="用户名或姓名"
                    value={searchDraft}
                    maxLength={100}
                    disabled={saving}
                    onChange={(event) => setSearchDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault()
                        findCandidates()
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    disabled={saving}
                    onClick={() => findCandidates()}
                  >
                    <Search className="size-4" />
                    查找
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <label htmlFor="mcp-user" className="text-sm font-medium">
                  中台账号
                </label>
                <Select
                  id="mcp-user"
                  required
                  value={selectedUser?.id ?? ""}
                  disabled={saving || candidateLoading || !!candidateError}
                  onChange={(event) => {
                    const candidate =
                      candidates?.items.find(
                        (item) => item.id === Number(event.target.value)
                      ) ?? null
                    setSelectedUser(candidate)
                    setProfile("products")
                  }}
                >
                  <option value="">
                    {candidateLoading ? "正在查找…" : "请选择账号"}
                  </option>
                  {selectedUser &&
                  !candidates?.items.some(
                    (item) => item.id === selectedUser.id
                  ) ? (
                    <option value={selectedUser.id}>
                      {selectedUser.username} · {selectedUser.department_code}
                    </option>
                  ) : null}
                  {candidates?.items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.username} · {item.display_name} ·{" "}
                      {item.department_code}
                    </option>
                  ))}
                </Select>
                {candidateError ? (
                  <p role="alert" className="text-xs text-destructive">
                    {candidateError}
                  </p>
                ) : (
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{candidates?.total ?? 0} 个符合条件的账号</span>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={
                          candidateLoading || saving || candidatePage <= 1
                        }
                        onClick={() => findCandidates(candidatePage - 1)}
                      >
                        上一组
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={
                          candidateLoading ||
                          saving ||
                          candidatePage * 30 >= (candidates?.total ?? 0)
                        }
                        onClick={() => findCandidates(candidatePage + 1)}
                      >
                        下一组
                      </Button>
                    </div>
                  </div>
                )}
              </div>
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
                    <option value="products">商品档案</option>
                    {selectedUser?.profiles.includes("design") ? (
                      <option value="design">商品档案 + 美工文案</option>
                    ) : null}
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
              <p className="rounded-lg bg-muted/50 p-3 text-xs leading-6 text-muted-foreground">
                默认有效期为 30 天，可设置 1～90 天或选择永久有效。
                查询结果会进入员工使用的模型上下文，请确认该账号的数据使用范围。不要把
                rathole 隧道密钥当作个人 Token。
              </p>
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
                  disabled={saving || !selectedUser || !label.trim()}
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
            if (!open) {
              setIssued(null)
              setCopied(false)
              setCopyError("")
            }
          }}
        >
          <DialogContent>
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
                  readOnly
                  autoComplete="off"
                  spellCheck={false}
                  value={issued.token}
                  onFocus={(event) => event.target.select()}
                  className="min-h-28 w-full resize-none rounded-lg border border-border bg-muted p-4 font-mono text-sm break-all focus-visible:outline-2 focus-visible:outline-ring"
                />
                <p className="text-xs text-muted-foreground">
                  到期时间：
                  {issued.item.expires_at === null
                    ? "永久有效"
                    : `${dateLabel(issued.item.expires_at)}（北京时间）`}
                </p>
                {copyError ? (
                  <p role="alert" className="text-xs text-destructive">
                    {copyError}
                  </p>
                ) : null}
                <DialogFooter>
                  <Button variant="outline" onClick={() => setIssued(null)}>
                    我已保存，关闭
                  </Button>
                  <Button onClick={() => void copyToken()}>
                    {copied ? (
                      <Check className="size-4" />
                    ) : (
                      <Copy className="size-4" />
                    )}
                    {copied ? "已复制" : "复制 Token"}
                  </Button>
                </DialogFooter>
              </div>
            ) : null}
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
