# UCloud US3 商品图片同步说明

## 功能范围

- 商品图片仍以局域网共享目录为源文件。
- 后端只同步商品档案当前实际引用的图片，避免千百度男女鞋共用目录被重复整目录上传。
- 新增或内容发生变化的图片才会上传，远端已有且本地未变化的图片会跳过。
- US3 上传失败不会删除或修改共享目录中的原图。
- 图片页面地址保持 `/images/serve/{brand}/{path}` 不变。
- 已同步图片由后端生成短期私有签名地址，并让浏览器直接从 US3 读取。
- 尚未同步、同步失败或 US3 未配置时，继续从原共享目录读取。

## US3 目录

| 目录 | 品牌 |
| --- | --- |
| `cbanner_mens/` | 千百度男鞋 |
| `cbanner_womens/` | 千百度女鞋 |
| `yandou/` | 烟斗 |
| `eblan/` | 伊伴 |
| `smiley/` | 笑脸 |
| `ni/` | NI |

系统使用 `cbanner_womens`，不要使用少一个 `s` 的 `cbanner_women`。

## 配置

配置存放在 `backend/.env`，密钥不得提交到 Git：

```env
UCLOUD_US3_PUBLIC_KEY=
UCLOUD_US3_PRIVATE_KEY=
UCLOUD_US3_BUCKET=hede-img
UCLOUD_US3_ENDPOINT=https://hede-img.cn-sh2.ufileos.com

# 以下配置可省略
UCLOUD_US3_IMAGE_PREFIX=
UCLOUD_US3_SIGNED_URL_EXPIRES=3600
UCLOUD_US3_TIMEOUT_SECONDS=60
UCLOUD_US3_SYNC_WORKERS=4
```

`UCLOUD_US3_IMAGE_PREFIX` 默认留空，因此品牌目录直接位于 Bucket 根目录。

## 手工执行

在 `backend` 目录运行预检，预检不会上传文件：

```powershell
uv run python -m scripts.sync_product_images_us3 --dry-run
```

执行完整增量同步：

```powershell
uv run python -m scripts.sync_product_images_us3
```

只同步某个品牌：

```powershell
uv run python -m scripts.sync_product_images_us3 --brand cbanner_womens
```

忽略本地同步清单并重新上传：

```powershell
uv run python -m scripts.sync_product_images_us3 --force
```

排查连接时可限制本次上传数量：

```powershell
uv run python -m scripts.sync_product_images_us3 --limit 1
```

## 定时任务

现有 Windows 定时任务 `HedeRefreshProductImages` 每天 `23:00` 执行
`backend/scripts/refresh_product_images_daily.cmd`。任务现在依次执行：

1. 扫描共享图片目录并回填商品档案缺失的本地图片路径。
2. 将商品档案引用的新图片或已变化图片增量同步到 US3。
3. 将结果写入 `backend/logs/refresh_product_images.log` 和定时任务运行记录。

## 增量清单

同步状态保存在本机：

```text
backend/.us3_image_sync_manifest.json
```

清单记录对象键、本地文件大小和最后修改时间。它已加入 `.gitignore`。系统不会根据清单自动删除 US3 文件；远端删除必须单独确认，避免误删仍在使用的图片。

## 当前验证

- 预检识别到 27,170 条去重图片引用。
- 其中 27,108 张本地文件可以同步。
- 62 条数据库图片路径当前找不到对应本地文件，会继续使用现有缺图状态。
- 已完成 1 张真实上传及私有签名读取测试，US3 返回 `200 image/jpeg`。
