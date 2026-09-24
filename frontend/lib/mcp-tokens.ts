export type McpProfile = "products" | "design" | "finance" | "merchandise" | "operation" | "development"

export type McpTokenItem = {
  id: number
  user_id: number
  username: string
  display_name: string
  department_code: string
  label: string
  profile: McpProfile
  state: "active" | "expired" | "revoked" | "blocked"
  created_at: string
  expires_at: string | null
  revoked_at: string | null
}

export type McpCandidate = {
  id: number
  username: string
  display_name: string
  department_code: string
  profiles: McpProfile[]
}

export type McpPage<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
}
export type IssuedMcpToken = { token: string; item: McpTokenItem }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/auth/admin/mcp-tokens${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-Mcp-Admin": "1" },
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown
    } | null
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "操作未完成，请检查表单或刷新列表确认状态"
    )
  }
  return response.json() as Promise<T>
}

export function listMcpTokens(page: number) {
  return request<McpPage<McpTokenItem>>(`?page=${page}&page_size=20`)
}

export function listMcpCandidates(query: string, page: number) {
  const search = new URLSearchParams({ query, page: String(page) })
  return request<McpPage<McpCandidate>>(`/users?${search.toString()}`)
}

export function issueMcpToken(payload: {
  user_id: number
  profile: McpProfile
  days: number | null
  label: string
}) {
  return request<IssuedMcpToken>("", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function revokeMcpToken(id: number) {
  return request<{ changed: boolean; message: string }>(`/${id}/revoke`, {
    method: "POST",
    body: "{}",
  })
}
