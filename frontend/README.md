# Next.js template

This is a Next.js template with shadcn/ui.

## 生产启动

在当前目录执行 `pnpm run build` 后，再执行 `pnpm run start`。生产模式不会自动加载源码修改，需要重新构建并重启前端。

需要保留正在运行的构建时，可在 PowerShell 中先设置 `$env:NEXT_DIST_DIR='.next-release-日期'`，再构建并启动；两条命令必须使用相同的 `NEXT_DIST_DIR`。未设置时仍使用 `.next`，后端地址与端口配置不变。

## Server Action 报错排查

本项目没有使用 Next.js Server Actions，业务保存和文件导入通过 `/api/*` 代理到后端。`Failed to find Server Action` 不一定由新旧部署混用造成：没有 `Next-Action` 请求头的 multipart POST 如果误发到页面地址，也会触发 Next.js 的同名错误。

`proxy.ts` 拒绝带 `Next-Action` 头的请求，并对非 `/api` 路径的 POST 返回 405，避免这类请求进入页面的 Server Action 处理。正常页面访问、API 提交及原有导入大小限制保留。调整代理源码后，生产环境需重新构建并重启前端才能生效。若还需确认请求来源，应核对同一时刻反向代理访问日志中的方法、路径、客户端 IP 和 User-Agent；仅凭错误堆栈不能判定来源。

## Adding components

To add components to your app, run the following command:

```bash
npx shadcn@latest add button
```

This will place the ui components in the `components` directory.

## Using components

To use the components in your app, import them as follows:

```tsx
import { Button } from "@/components/ui/button";
```
