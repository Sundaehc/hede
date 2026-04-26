import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

type ImageLookupStatusProps = {
  status: "idle" | "loading" | "success" | "warning" | "error"
  message: string | null
}

export function ImageLookupStatus({ status, message }: ImageLookupStatusProps) {
  if (status === "idle" || !message) {
    return null
  }

  const title =
    status === "loading"
      ? "图片查询中"
      : status === "success"
        ? "已匹配图片"
        : status === "warning"
          ? "未找到图片"
          : "查询失败"

  const className =
    status === "success"
      ? "border-emerald-500/40"
      : status === "warning"
        ? "border-amber-500/40"
        : status === "error"
          ? "border-destructive/30"
          : undefined

  return (
    <Alert className={className}>
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
