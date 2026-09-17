# Hede 鞋盒标签 Windows 服务

采购单鞋盒标签不再经过 Chrome 打印预览。本服务把网页生成的 `640×480` 黑白点阵以 RAW TSPL 发送到 Windows 打印队列，固定对应 `80×60 mm` 标签，避免 A4、页边距、缩放和方向干扰。

## 安装电脑

服务必须运行在“实际点击打印，且 Windows 中已经安装 `TSCTTP-244 Pro` 打印队列”的电脑上。打印机通过 USB 连接另一台电脑时，有两种用法：在那台电脑上打开系统并打印；或者先把打印机共享并安装到当前电脑，再在当前电脑运行本服务。浏览器与打印服务必须位于同一台电脑，因为服务只监听 `127.0.0.1`。

1. 在 Windows 的“打印机和扫描仪”中确认打印机名称为 `TSCTTP-244 Pro`，纸张为宽 `80 mm`、高 `60 mm`。打印机应安装为所有用户可见的本机打印队列。
2. 解压 `HedePrintAgentService.zip`，双击 `Install-Service.cmd`，在 Windows 权限提示中选择“是”。
3. 安装脚本会把程序安装到 `C:\Program Files\Hede\PrintAgent`，并注册为开机自动启动的 Windows 服务。
4. 双击 `Check-Service.cmd`，应看到服务为 `RUNNING`，接口返回 `"status":"ready"`。
5. 回到采购单明细点击“打印”。任务会直接进入 `TSCTTP-244 Pro` 队列，不再弹出浏览器打印预览。

安装后没有黑色窗口，也不需要用户登录 Windows。服务异常退出时会分别在 5 秒、15 秒和 60 秒后自动重启。

## 配置

配置文件位于 `C:\ProgramData\HedePrintAgent\config.json`：

```json
{
  "printer_name": "TSCTTP-244 Pro",
  "port": 18120,
  "gap_mm": 2,
  "direction": 1,
  "invert_bitmap": true,
  "allowed_origins": [
    "https://platform.hedespace.com",
    "http://127.0.0.1:3001",
    "http://localhost:3001"
  ]
}
```

字段说明：

| 字段 | 默认值 | 用途 |
| --- | --- | --- |
| `printer_name` | `TSCTTP-244 Pro` | Windows 打印机名称 |
| `port` | `18120` | 仅监听本机回环地址的端口 |
| `gap_mm` | `2` | 标签间隙，单位 mm |
| `direction` | `1` | TSPL 打印方向，可设为 `0` 或 `1` |
| `invert_bitmap` | `true` | 反转点阵，使 TSCTTP-244 Pro 输出白底黑字 |
| `allowed_origins` | 平台域名及本地开发地址 | 允许调用打印服务的网页来源 |

修改配置后双击 `Restart-Service.cmd` 才会生效。如正式访问域名不是 `https://platform.hedespace.com`，在 `allowed_origins` 中追加实际完整来源。服务始终只监听 `127.0.0.1`，局域网其他电脑不能直接调用。

## 生成独立 EXE

打印电脑没有 Python 时，可在开发电脑执行：

```powershell
cd E:\hede\backend
uv pip install pyinstaller
.\print_agent\build_tsc_print_agent.cmd
```

构建结果为 `backend\dist\HedePrintAgentService.zip`，将整个 ZIP 复制到打印电脑并解压，不要只复制 EXE。

## 日常维护

- `Check-Service.cmd`：显示 Windows 服务和打印机接口状态。
- `Restart-Service.cmd`：修改配置后重新加载服务。
- `Uninstall-Service.cmd`：移除服务和程序，配置与日志默认保留。
- 服务日志：`C:\ProgramData\HedePrintAgent\logs\service.log`，单文件最大 5 MB，保留 5 份历史日志。

## 常见问题

- 提示“本机打印服务未启动”：运行 `Check-Service.cmd`，确认服务为 `RUNNING`。
- 提示找不到打印机：Windows 打印机名称必须与配置中的 `printer_name` 完全一致。
- 标签上下颠倒：把配置中的 `direction` 在 `0` 和 `1` 之间切换，然后运行 `Restart-Service.cmd`。
- 每张标签纵向偏移：按实际标签纸修改 `gap_mm`，并先在打印机驱动中完成纸张校准。
- 如果更换打印机后又出现颜色反转，可把 `invert_bitmap` 改为 `false`，再运行 `Restart-Service.cmd`。
- 服务运行但找不到打印机：确认该打印机不是仅当前登录用户可见的网络映射，必要时将驱动和打印队列安装为本机所有用户可见。
