import { type NextRequest, NextResponse } from "next/server"
import { PROXY_MAX_BODY_BYTES } from "@/lib/upload-limits.mjs"

export function hasUnexpectedServerActionHeader(headers: Headers) {
  return headers.has("next-action")
}

export function proxy(request: NextRequest) {
  if (hasUnexpectedServerActionHeader(request.headers)) {
    return NextResponse.json(
      { detail: "当前系统不支持 Server Action 请求" },
      { status: 400 },
    )
  }

  // All application submissions go through the backend API. A headerless
  // multipart POST to a page would otherwise enter Next's Server Action handler.
  const pathname = request.nextUrl.pathname
  const isApiRequest = pathname === "/api" || pathname.startsWith("/api/")
  if (request.method === "POST" && !isApiRequest) {
    return NextResponse.json(
      { detail: "页面地址不支持 POST 请求，请通过 /api 接口提交" },
      { status: 405, headers: { Allow: "GET, HEAD, OPTIONS" } },
    )
  }

  const contentLength = Number(request.headers.get("content-length"))
  if (Number.isFinite(contentLength) && contentLength > PROXY_MAX_BODY_BYTES) {
    return NextResponse.json(
      { detail: "请求内容过大，单个导入文件不能超过 100MB，请拆分后重试" },
      { status: 413 },
    )
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
}
