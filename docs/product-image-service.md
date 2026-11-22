# 杭州视觉管理系统取图接口

由中台维护人员更新并手动重载后端后启用。无需重新构建前端。新建专用表 `product_image_service_tokens`，后端初始化会幂等建表；使用迁移管理的环境对应版本为 `20261121_0088`。若环境的 Alembic 版本落后，沿用后端初始化，不要为本功能补跑旧迁移。回退可先撤销令牌并部署旧版；降级移除凭证表会删除令牌记录，不影响商品档案。

取图仅允许以下 HTTPS 请求，`{货号}` 取只读 MCP 商品档案中的 `sku`，作为单个 URL 路径段编码：

```text
GET https://platform.hedespace.com/api/images/serve/cbanner_womens/{货号}.jpg
GET https://platform.hedespace.com/api/images/serve/smiley/{货号}.jpg
Authorization: Bearer <商品图片服务令牌>
```

令牌独立于中台账号和 MCP。服务端先按品牌和货号查有效商品档案，只下载档案关联的图片。URL 末尾的 `.jpg` 是接口约定，实际内容格式以响应的 `Content-Type` 为准。没有有效令牌返回 `401`，带服务令牌访问其他方法、品牌或接口返回 `403`，档案或图片不存在时返回 `404`。

- 已同步且可生成 HTTPS 签名链接：先返回 `307`。从 `Location` 另发 GET 取图，不携带中台的 `Authorization` 或 Cookie，也不要记录带签名的 URL。签名最多有效 60 秒，使用后丢弃；每次同步从原接口重新请求。
- 未同步、签名不可用或未配置 HTTPS 对象存储时，中台尝试直接返回图片。直接返回时图片文件的 `ETag`、`Last-Modified` 来自文件；跳转时以最终图片响应头为准，`307` 本身不表示图片版本。两个样例的对象存储都返回了 `ETag` 和 `Last-Modified`，但带相同 `ETag` 的 `If-None-Match` 请求实测仍返回 `200`。可用返回的 `ETag` 或内容哈希判断是否要重新生成缩略图；当前不能靠 `304` 省去传输。
- 令牌撤销后，后续原接口请求立即拒绝；已经签发的对象存储 URL 可用至其到期，已经下载的副本不受影响。

维护人员在 `backend` 目录的受控交互终端签发，默认建议 30 天，允许 1–90 天。签发不需要为应用开通中台账号或 MCP 权限，签发和撤销后也不需要再重启。数据库仅保存令牌哈希，明文只显示一次，直接存入已批准的内部凭证库，再授权给定时任务的运行身份。关闭命令输出采集、录屏和会话转录，不通过聊天、邮件或工单传递明文。

```powershell
uv run python -m product_image_token_admin issue --label '杭州视觉管理系统' --days 30
uv run python -m product_image_token_admin list
uv run python -m product_image_token_admin revoke <令牌ID>
```

上线验收：对 `cbanner_womens/RZ954054M02.jpg` 和 `smiley/6362022340600.jpg` 均先查看原接口状态，按上文处理可能的 `307`，确认最终为 `200` 且能解码为图片；再确认无凭证返回 `401`、其他品牌与 `POST` 返回 `403`。撤销验收请用独立的临时令牌，避免影响定时任务。

2026-11-21 隔离验收：使用真实档案的只读图片关联、隔离数据库中的临时服务令牌以及真实对象存储。两款均返回 `307 → 200` 且解码为 JPEG，尺寸分别为 `435 × 287`、`1799 × 1014`。项目相关测试 34 项通过，5 项因没有独立的 PostgreSQL 测试库跳过。此验收不代表生产域名已启用服务令牌。
