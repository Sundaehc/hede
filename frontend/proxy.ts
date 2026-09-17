import { type NextRequest, NextResponse } from "next/server"

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

  return NextResponse.next()
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
}
