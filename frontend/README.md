# Next.js template

This is a Next.js template with shadcn/ui.

## 生产启动

在当前目录执行 `pnpm run build` 后，再执行 `pnpm run start`。生产模式不会自动加载源码修改，需要重新构建并重启前端。

需要保留正在运行的构建时，可在 PowerShell 中先设置 `$env:NEXT_DIST_DIR='.next-release-日期'`，再构建并启动；两条命令必须使用相同的 `NEXT_DIST_DIR`。未设置时仍使用 `.next`，后端地址与端口配置不变。

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
