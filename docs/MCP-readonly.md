# Codex只读数据库MCP

## 第一版范围

独立进程与独立Python环境，不挂载现有FastAPI，不调用豆包或其他模型。由员工Codex根据工具提供的数据结构生成SQL，再交由服务端校验执行。

仅提供 `list_datasets`、`describe_dataset`、`query_readonly`。默认仅监听本机 `127.0.0.1:8765/mcp`，Streamable HTTP、无会话、JSON响应。采用预签发个人Bearer Token，不提供OAuth登录/自动注册。Token可通过中台超级管理员页面或本机CLI管理；管理接口不作为MCP工具提供。

| 凭证profile | 可查询数据 | 开通条件 |
| --- | --- | --- |
| `products` | `products`商品档案视图 | 活跃系统用户且有 `product.view` 或 `*` 权限 |
| `design` | 商品档案、`copywriting`当前文案记录、`copywriting_history`成功历史 | 上述条件且为美工部或超级管理员 |
| `finance` | 商品档案、库存/供应商/采购只读视图、商品成本及供应商视图 | 财务部且有 `product.view`、`inventory.view`、`purchase.view` |
| `merchandise` | 商品档案、精细表/销售/采购/库存/商品货品及基础资料视图 | 商品部现有权限 |
| `operation` | 商品档案、精细表/销售/采购及商品货品视图 | 运营部现有权限；不开放进销存和基础资料维护表 |
| `development` | 商品档案、精细表/销售/采购/库存/商品货品及基础资料视图 | 开发部现有权限 |

各部门范围只开放与中台现有部门权限对应的安全视图；财务、商品、运营、开发四部门按现有商品成本可见规则开放成本及供应商视图，美工、客服不开放。所有范围均不开放图片路径、系统提示词、原始JSON、账号/会话及订单个人敏感字段。查询权限不等于网站全部权限；超级管理员在MCP也只获得签发profile的范围。商品视图包含已有内置品牌与初始化时启用的自定义品牌，排除删除商品和商品排除清单。自由文本可能含员工录入的敏感内容，启用前需审查允许发送给Codex模型的数据。

## 隔离与防护

- 旧的3个专用角色继续保留；新增 `hede_mcp_finance`、`hede_mcp_merchandise`、`hede_mcp_operation`、`hede_mcp_development` 四个部门专用角色，分别只SELECT本部门安全视图。`hede_mcp_control`仅SELECT身份投影视图、INSERT审计表。不把管理员连接用于运行时查询。角色默认只读、无角色继承、无超级权限；视图由初始化管理员所有，采用security_barrier，不给调用者底层表权限。
- 启动校验角色、默认只读、额外表/列权限、schema/数据库CREATE权限及可执行的自定义函数。发现PUBLIC过度授权时拒绝启动，不自动修改其他业务用户授权；由管理员先审查和收紧。不要改为跳过检查，也不要换成管理员连接。系统内置函数仍由SQL语法/函数白名单限制。
- SQL经SQLGlot PostgreSQL解析，单条SELECT/CTE/集合查询，字段校验、授权数据集映射、命名参数绑定；拒绝写入型CTE、多语句、原始表、其他schema、SELECT INTO、FOR UPDATE、递归、任意函数、危险类型、CROSS JOIN和缺少ON/USING的JOIN。第一版刻意不支持窗口函数、正则、EXPLAIN等未列入白名单语法。
- 每次查询READ ONLY事务，业务时区Asia/Shanghai，statement_timeout=10秒、lock_timeout=1秒、200行、512KB数据结果上限、全局4个HTTP并发请求、每Token每分钟60次请求。返回 `truncated=true` 不代表已取全量；缩小范围或带明确排序分页。大聚合仍可能消耗资源，正式开放建议从少数用户开始。512KB是结果数据预算，MCP协议包装可能额外占用空间。
- Token随机生成，数据库仅保存SHA-256；每次HTTP请求重新检查撤销、到期、用户状态和当前角色权限。已在执行的查询不会被撤销动作立刻中断，下一次请求拒绝。
- 查询审计记录request_id、用户ID、Token ID、工具、SQL摘要、状态、行数与耗时，不记录完整SQL、参数、凭证或结果正文。审计不可用则不执行/不返回查询结果。Token通过中台超级管理员页面或本机CLI发放撤销，不能用MCP调用。网页签发/撤销与用户管理操作日志同事务提交，审计失败则回滚；日志不包含Token正文或哈希。
- Host/Origin明确白名单；不允许通配符。不接受查询字符串Token，不在URL中传凭证。服务不会把数据库异常堆栈和内部地址返回客户端。

## 安装与初始化（管理员在本机执行）

在 `E:\hede\backend` 打开PowerShell：

```powershell
uv venv .venv-mcp --python .venv\Scripts\python.exe
uv pip install --python .venv-mcp\Scripts\python.exe -r requirements-mcp.txt
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin setup
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin doctor
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin setup --execute
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin verify
```

不要覆盖或同步现有 `.venv`。`setup` 默认只说明变更，`--execute` 才连接 `backend/.env` 的 `DATABASE_URL` 创建账号、schema、视图、凭证与审计表，并在同一 `.env` 追加以下专用配置（不会打印密码）：

```dotenv
MCP_PRODUCTS_DATABASE_URL='postgresql+psycopg://hede_mcp_products:SECRET@HOST:5432/DB'
MCP_DESIGN_DATABASE_URL='postgresql+psycopg://hede_mcp_design:SECRET@HOST:5432/DB'
MCP_CONTROL_DATABASE_URL='postgresql+psycopg://hede_mcp_control:SECRET@HOST:5432/DB'
```

初始化需要能创建角色和视图的管理员；已有同名角色/schema/配置则拒绝覆盖，防止误重置凭证。依赖现有 `auth_users`、`auth_roles`、商品档案、文案及历史表，不修改这些表的数据。只有新表和视图；不执行全库GRANT SELECT，不创建无条件全库只读账号。

`doctor`只读诊断现有PUBLIC函数执行权、表/列权限、schema/数据库CREATE授权及必需表，输出对象名称但不输出数据库密码或业务记录。`setup --execute`在创建任何角色之前再次检查；存在待审核权限时直接停止。诊断列出函数不代表函数有漏洞，可能是扩展或触发器；不能简单全库REVOKE，否则可能影响网站、触发器和索引。管理员需确认实际业务账号及扩展依赖后另行规划权限收紧，不由本工具代做。

2026-09-22这37个函数的专项审查、隔离演练和定向变更/回滚方案见 `docs/MCP-permission-review-20260922.md`。用户批准后，已于当日北京时间17:55完成正式撤权与MCP初始化，随后启动后台MCP，并验证本机及公网入口到达认证层。**本机不要重复执行apply.sql或setup --execute**；后续用doctor/verify检查。尚未签发员工Token或配置开机自启，详细部署记录见该审查报告。

`.env`含数据库秘密，仅服务运行账号/管理员可读，需使用Windows文件权限保护，不能共享给员工。异常发生在提交数据库后写.env时，恢复文件为 `backend/.env.mcp-pending`（同样敏感且被Git忽略）。确认恢复后删除，不重复setup。

### 部门范围升级（已有部署）

已有三账号部署不要重复执行 `setup --execute`。先停止独立MCP，备份数据库和 `backend/.env`，在本机 `backend` 目录执行预览：

```powershell
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin upgrade-department-scope
```

确认范围和备份无误后，执行一次：

```powershell
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin upgrade-department-scope --execute
```

命令会新增 `hede_mcp_finance`、`hede_mcp_merchandise`、`hede_mcp_operation`、`hede_mcp_development` 四个数据库只读角色、安全视图及Token范围，并把四个连接追加到 `backend/.env`；不修改现有Token。执行完成后由管理员手动更新并重启MCP，再运行 `verify`。如果 `.env.mcp-department-pending` 留下，先人工核对恢复，不要重复执行升级。

## 签发个人凭证

### 中台页面（超级管理员）

入口：**系统管理 → 用户管理 → MCP Token 管理**，页面路径 `/admin/mcp-tokens`。该入口保留现有侧栏结构，不新增系统管理一级菜单。页面及API都只允许启用的超级管理员访问；即使普通角色具有system.admin权限，也不能签发凭证。

1. 点击“签发 Token”，按用户名/姓名查找已启用且有商品查看权限的中台账号。
2. 选择“商品档案”“商品档案 + 美工文案”或当前账号所属部门范围；后端签发时再次校验当前部门和权限。
3. 设置1～90天有效期或勾选“永久有效”，再填写用途备注并确认签发。默认仍为30天。
4. 明文仅在成功弹窗中展示，可复制或手动选择；关闭、离开页面或失去管理员身份后不再展示，不写入浏览器持久存储。请通过安全渠道交付给本人。
5. 列表显示所有网页/CLI签发的凭证、所属账号、范围、到期时间及有效/到期/撤销/账号权限失效状态；不能重新查看明文。撤销需二次确认，后续请求即被拒绝，已执行中的查询不保证立即中断。

签发或撤销不需要重启MCP。不自动重试签发请求；若网络中断、没有拿到明文，先刷新列表确认签发状态，必要时撤销该记录后重新签发，避免留下未知凭证。

管理接口位于 `/auth/admin/mcp-tokens`，使用中台原有会话认证。写入要求JSON及专用请求头并校验Origin，页面使用no-store，签发/列表响应禁止缓存。用真实中台HTTPS域名访问；若新增域名，先把可信来源加入后端FRONTEND_ORIGIN配置，不放宽成通配符。HTTP局域网页面的剪贴板不可用时可以手动复制，但敏感凭证应优先通过HTTPS签发和交付。

此页面不负责数据库初始化、撤权、隧道配置或启动服务。未初始化返回明确提示，不会自动建表。后端不需要安装MCP SDK。新增页面/接口需要由管理员按现有方式更新并手动重启中台前后端；生产前端应先按现有发布流程构建。独立MCP无需因为增加网页管理而重启，也不需要改rathole或Nginx。

### 本机CLI（保留）

```powershell
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin issue-token --username 实际系统用户名 --profile products --days 30 --label 员工Codex
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin issue-token --username 美工系统用户名 --profile design --days 30
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin issue-token --username 财务系统用户名 --profile finance --days 30
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin list-tokens
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin revoke-token --id 具体TokenID
```

有效期默认30天，可设置1至90天，也可使用 `--permanent` 签发永久Token。永久Token不会自动到期，但仍受手动撤销、账号停用、账号权限变化和文案范围限制。永久状态在数据库中以 `expires_at IS NULL` 保存，列表会显示“永久有效”。签发命令仅当次显示明文Token，请在自己的终端运行，不在聊天/共享日志里发放，不与rathole隧道Token混用。轮换用新签发＋撤销旧Token。新增自定义品牌表或调整排除清单后执行 `readonly_mcp.admin refresh-views`，再 `verify`；现有表内数据更新无需刷新视图。

### 启用永久有效（已有部署）

已有部署不要重复执行 `setup --execute`。先将本次代码更新到运行MCP的电脑，并手动重启独立MCP服务，使其识别 `expires_at` 为空的Token；然后在该电脑的 `backend` 目录执行：

```powershell
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin upgrade-token-expiry
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin upgrade-token-expiry --execute
```

第一条只预览，第二条仅将 `mcp_private.tokens.expires_at` 改为允许为空，幂等执行，不修改已有Token、账号、视图、权限或隧道配置。确认升级成功后，网页勾选“永久有效”或执行：

```powershell
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin issue-token --username 实际系统用户名 --profile products --permanent --label 员工Codex
```

如果独立MCP还在运行旧代码，不要签发永久Token；旧进程无法正确处理空到期时间。普通30天/1～90天Token的行为保持不变。

## 本机启动

```powershell
.\scripts\start_readonly_mcp.cmd
```

脚本先校验数据库角色，再前台启动独立MCP进程。不会停止或重启现有前后端。手动Ctrl+C可停止MCP。需要开机常驻时，再由管理员配置Windows服务/计划任务，并保证数据库先启动、电脑不休眠；本实现不会自动注册开机任务。

## 复用rathole

```text
员工Codex → HTTPS公网域名 → 服务器Nginx → 127.0.0.1:18765
        → rathole加密隧道 → 你电脑127.0.0.1:8765 → 本机PostgreSQL
```

参考 `backend/readonly_mcp/deploy/` 的两份rathole片段，追加到现有server/client配置，不替换现有连接与其他服务。隧道Token两端一致但必须独立于员工Token。服务器转发端口18765只监听回环，不开放到公网；只开放HTTPS 443，不转发数据库5432。

rathole原有全局传输必须核验已开启TLS或Noise；只在公网终止HTTPS不足以保护隧道后半段。这里不覆盖现有传输配置，避免影响其他服务。若Nginx和rathole运行在不同Docker容器，回环地址不能跨容器使用，需改为受限的容器网络地址，不直接使用示例。

Nginx示例使用 `mcp.example.com` 占位域名及证书路径。部署前替换真实域名/证书，验证配置后再重载。不要用HTTP公网传员工Token。MCP服务的 `backend/.env` 再追加：

```dotenv
MCP_PORT=8765
MCP_ALLOWED_HOSTS=127.0.0.1:8765,localhost:8765,mcp.example.com
MCP_ALLOWED_ORIGINS=https://mcp.example.com
```

域名与代理转发的Host必须一致；若包含非默认端口，白名单需含对应端口。客户端没有Origin头可以正常访问；有Origin时必须匹配。MCP配置变动只重启MCP，不用重启网站。部署前确认8765和18765未被其他服务占用。

## 员工Codex配置

Windows 员工端按 [Codex CLI 接入指南](MCP-Codex-CLI.md) 操作，包含一次性保存 Token、配置、验证和报错排查。

将 `deploy/codex.example.toml` 内容按实际域名追加到员工 `~/.codex/config.toml`。个人Token放 `HEDE_MCP_TOKEN` 环境变量，不能提交到代码库，设置后重新启动Codex以继承环境。远程接入不需要员工安装Python、PostgreSQL或rathole；不能使用 `codex mcp login`，该版本采用预签发Bearer Token而不是OAuth。

```toml
[mcp_servers.hede_readonly]
url = "https://mcp.example.com/mcp"
bearer_token_env_var = "HEDE_MCP_TOKEN"
tool_timeout_sec = 30
```

先让Codex调用 `list_datasets`，再 `describe_dataset("products")`。示例调用：

```json
{"sql":"SELECT brand,id,sku,product_name,color FROM products WHERE sku=:sku ORDER BY brand,id","params":{"sku":"RQ464090M73"}}
```

查询结果会进入员工Codex上下文，不因数据库在本地就意味着模型服务收不到数据。先审核模型使用政策和字段再给员工开通。

## 验证

测试依赖装在独立环境：

```powershell
uv pip install --python .venv-mcp\Scripts\python.exe pytest httpx
.\.venv-mcp\Scripts\python.exe -m pytest readonly_mcp/tests --confcutdir=readonly_mcp -q -p no:cacheprovider
```

默认仅模拟数据库，不读取 `.env` 的管理员连接。真实PostgreSQL测试只接受 `MCP_TEST_DATABASE_URL` 指向 `127.0.0.1:55439/postgres`，还强制检查data_directory位于 `backend/logs/mcp-pg-test-*` 独立集群；绝不能把生产库设置为测试库。测试会创建测试数据库与同名角色，应每轮使用新临时集群，结束后关闭。

官方参考（示例与SDK接口据此核对）：

```text
https://developers.openai.com/codex/mcp
https://py.sdk.modelcontextprotocol.io/run/deploy/
https://github.com/rathole-org/rathole
```
