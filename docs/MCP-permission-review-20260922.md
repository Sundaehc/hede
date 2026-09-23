# MCP函数权限审查（2026-09-22）

## 结论与执行状态

审查时间：2026-09-22，北京时间。目标：现有后端 `backend/.env` 指向的PostgreSQL 18.3数据库。

**结论：在本次核实的账号和对象配置不变的前提下，可以仅撤销明确列出的37个函数对PUBLIC的EXECUTE授权，保留postgres账号、函数定义、触发器和索引。建议有条件执行，不需要删除函数、卸载pg_trgm或跳过MCP安全检查。**

审查阶段仅使用READ ONLY事务读取正式库，并在独立临时数据库演练。随后用户明确批准“执行并启动MCP”，已于2026-09-22北京时间17:55完成正式变更，详见下面的部署记录；未修改业务数据或重启现有前后端。

### 正式部署记录

- 已在单事务内执行限定37个函数的PUBLIC EXECUTE撤权，随后doctor返回 `ready_for_setup=true`，无额外权限或缺表问题。
- 原始ACL快照已备份至 `backend/logs/mcp-production-acl-before-20260922T095549Z.json`，不含数据库密码。
- 已创建 `hede_mcp_products`、`hede_mcp_design`、`hede_mcp_control`，初始化MCP视图、凭证与审计表；商品视图覆盖7个商品源。专用连接已追加至 `backend/.env`，未输出密码。
- verify通过；products账号查询商品视图、design账号查询当前文案与历史视图均成功，验证只返回常量，不输出业务记录。
- 17:57启动独立后台MCP，18:00确认仅监听 `127.0.0.1:8765`。本机及 `https://platform.hedespace.com/mcp` 的无凭证POST均返回预期401和unauthorized，HTTPS证书校验未跳过。
- 日志为 `backend/logs/mcp-server-20260922-175759.out.log` 和对应 `.err.log`，检查时无报错。尚未配置开机自启，后台进程不等同于Windows服务。
- 尚未签发员工Token，故未执行携带真实员工凭证的公网工具调用；公网401只证明请求能到认证入口，不证明授权查询或rathole隧道加密配置正确。
- **正式库已初始化，不要重复执行apply.sql或setup --execute。** 后续检查用doctor/verify，员工开通按部署文档签发个人Token。

## 撤权前已核实事实

- 当前唯一非系统数据库角色为postgres，是超级用户；后端配置和审查时的数据库连接均使用postgres。没有额外业务账号、MCP账号或MCP schema。
- 37个函数全部归postgres所有、全部为SECURITY INVOKER，不存在SECURITY DEFINER函数。
- 37个函数的原始 `proacl` 全部为NULL，实际授权为PUBLIC EXECUTE和postgres所有者EXECUTE，无额外显式授权、无PUBLIC grant option。
- 31个函数属于 `pg_trgm 1.6`，语言C，绑定 `$libdir/pg_trgm`；与本机相同安装的独立临时库创建出的扩展定义校验值一致。未审计C二进制本身或声称排除扩展漏洞。
- 其余6个为PL/pgSQL业务函数：5个触发器函数和1个JSON转换辅助函数。已阅读正式库实际定义并与业务源代码调用关系核对。
- 5个触发器函数关联16个启用的非内部触发器：商品标识同步7个、明细关联1个、单据变更重关联1个、冷分区防写6个、更新时间1个。
- pg_trgm关联22个现有索引，全部 `indisvalid=true`、`indisready=true`，涉及10张表/分区。不是无用扩展，不能删除或卸载。
- 当前没有自定义默认权限；public schema仅给PUBLIC USAGE，不给CREATE；未发现PUBLIC业务表/列授权或数据库CREATE授权。

## 分类审查

### pg_trgm：31个函数

| 类别 | 数量 | 内容与结论 |
| --- | --- | --- |
| GIN索引支撑 | 4 | `gin_extract_query_trgm`、`gin_extract_value_trgm`、`gin_trgm_consistent`、`gin_trgm_triconsistent`；保留定义和索引，仅收紧直接调用权限。 |
| GiST/类型支撑 | 11 | `gtrgm_compress`、`gtrgm_consistent`、`gtrgm_decompress`、`gtrgm_distance`、`gtrgm_in`、`gtrgm_options`、`gtrgm_out`、`gtrgm_penalty`、`gtrgm_picksplit`、`gtrgm_same`、`gtrgm_union`。 |
| 相似度及其操作符实现 | 13 | `similarity`系列3个、`word_similarity`系列5个、`strict_word_similarity`系列5个；不属于MCP允许的SQL函数接口。 |
| 参数与trigram展示 | 3 | `set_limit`、`show_limit`、`show_trgm`；`set_limit`改变会话相似度阈值，不应概括为全部无副作用。 |

不存在“有PUBLIC授权就证明函数有漏洞”的结论。此次撤权是满足MCP最小直接执行权限边界，不是修补已证实的数据库漏洞。索引内部支撑调用不等同于给用户开放任意函数直接调用；独立库验证了撤权后现有业务账号GIN搜索和MCP允许的LIKE查询仍可执行。

### 业务函数：6个

| 函数 | 实际行为与依赖 | 审查意见 |
| --- | --- | --- |
| `smiley_copy_set_updated_at()` | 对 `smiley_product_copy_base` 的NEW记录设置updated_at。 | 保留触发器；不需让新MCP账号直接执行。 |
| `reject_cold_partition_write()` | 始终抛出SQLSTATE 55000，拒绝冷分区写入/清空。 | 是保护机制，不得禁用；涉及2023/2024订单与2024售后冷分区。 |
| `hede_replace_purchase_product_cache(json,text,text,text,text)` | 仅转换输入JSON的image_code/style_code，返回JSON，无数据库读写。 | 被商品标识同步函数调用；保留postgres执行权。 |
| `hede_sync_product_archive_identity()` | 新增/更新/停用商品标识；货号变化时更新关联单据明细、图片/款号缓存、单据时间。 | 有业务写入，必须保留触发器；撤销PUBLIC不撤销postgres所有者权限。 |
| `hede_link_purchase_order_detail_product()` | 读取单据、供应商、商品标识，更新NEW明细的货号与商品关联。 | 用于采购和其他单据；独立库覆盖采购及销售类型。 |
| `hede_refresh_document_product_links()` | 单据类型、供应商或raw_payload变化时更新明细，触发重新匹配商品。 | 保留AFTER UPDATE触发器；定义使用JSONB比较，未修改现有业务逻辑。 |

6个定义均未发现动态EXECUTE、SET ROLE、数据库外部连接或文件/网络访问调用。引用的业务表和辅助函数部分未加schema，亦未固定函数search_path；当前无PUBLIC CREATE且全部SECURITY INVOKER，不能据此认定已有提权漏洞。但未来若引入非受信schema、普通业务账号或SECURITY DEFINER，必须重新评估，不应原样套用本报告。

调用代码定位：`backend/domain/product_archive_identity_schema.py`、`backend/domain/order_history_tiering.py`、`backend/scripts/add_performance_indexes.py` 及相关索引迁移。PL/pgSQL正文调用不一定完整出现在pg_depend，因此同时审阅实际函数正文，未仅依赖系统依赖表。

## 影响与风险

1. 当前业务通过postgres执行，撤销PUBLIC EXECUTE后仍保留所有者权限及超级用户权限，预期不影响现有后端。独立库验证支持该判断，但不能代替生产全业务验收。
2. 新普通账号将不能直接执行这37个函数及相应需要执行权的操作符。未来若为其他系统建立普通账号，应按需要单独GRANT，不能恢复PUBLIC作为通用解决方式。
3. 此次不修改postgres超级用户配置；业务长期使用超级用户本身是另一项最小权限改进，不在本次范围内，也不会把该连接交给员工。
4. `CREATE OR REPLACE FUNCTION`保留原有权限，已演练；DROP后重建、扩展升级/重装或新建函数可能重新产生PUBLIC默认授权。以后迁移/扩展更新后重跑doctor和verify，不能只依赖此次一次性审查。
5. 本次没有修改全局默认授权，避免改变后续扩展/迁移行为。需要长期限制未来新函数时，另行评估创建角色的默认权限。
6. 元数据审查不证明不存在未连接的外部应用；不过当前全库没有其他自定义角色，外部应用若同样使用postgres也保留当前权限。若执行前账号发生变化，必须重新审查。

## 独立数据库演练结果

在同机独立临时集群 `127.0.0.1:55439`、单独数据库中执行，未使用生产业务行。只复制6个正式业务函数的DDL，pg_trgm从同版本安装包创建；其余业务表与记录为合成测试数据。

**32项断言全部通过：**

- 精确37函数清单、定义摘要匹配；多出账号、定义漂移或重复执行时拒绝变更，失败事务不遗留部分撤权。
- 定向撤销37个PUBLIC执行权后，postgres仍能执行相似度函数，商品插入与货号更新、JSON缓存同步、采购明细关联、销售明细关联、单据修改重新关联均正常。
- 更新时间触发器正常；冷归档INSERT及TRUNCATE仍抛出55000；业务LIKE查询实际执行计划使用GIN索引并返回预期数据。
- 再次CREATE OR REPLACE业务函数不恢复PUBLIC授权。
- doctor通过，实际调用MCP setup创建3个测试专用账号并通过verify；MCP商品LIKE查询成功。
- products/design角色没有这37个函数的直接执行权；直接调用相似度函数、读取原始业务表、写入授权视图被拒绝。
- 回滚在有MCP连接或出现后续ACL变更时拒绝执行；停止测试连接并恢复预期ACL后，回滚恢复37个函数的原始有效权限集合。

临时回归脚本在 `backend/logs/mcp-permission-review-check.py`，仅用于本次隔离演练，不是生产部署入口。正式库未运行写入型验收。

## 已准备的定向变更与回滚

目录：`backend/readonly_mcp/deploy/permissions-20260922/`。

- `manifest.sql`：37个完整函数签名与正式定义MD5快照。MD5仅用于检测定义漂移，不是安全签名。执行前检查所有者、安全模式及pg_trgm版本；不应单独运行此文件。
- `apply.sql`：单事务，只对清单函数REVOKE PUBLIC EXECUTE，使用RESTRICT而非CASCADE；没有全库REVOKE、DROP、ALTER FUNCTION正文或默认权限修改。额外角色/MCP已初始化/额外PUBLIC函数/原始ACL变化即拒绝。
- `rollback.sql`：恢复原有有效PUBLIC执行权限，保留函数和业务数据；不删除已初始化的MCP对象。原始proacl为NULL，回滚恢复的是等价有效授权而非NULL目录表示；禁止直接UPDATE系统目录。回滚后MCP安全检查将再次拒绝启动。

执行前需再次确认使用正确数据库、停止并发DDL/权限变更窗口。脚本有事务、定义摘要、lock_timeout和statement_timeout，但不代替部署协调或针对恶意并发管理员的保护。

仅在另行批准后，在Windows PowerShell运行；使用真实数据库名，管理员密码交互输入，不写入脚本：

```powershell
& 'D:\Postgresql\bin\psql.exe' -X -h 127.0.0.1 -p 5432 -U postgres -d '实际数据库名' -W -f 'E:\hede\backend\readonly_mcp\deploy\permissions-20260922\apply.sql'
```

若真实PostgreSQL主机/端口不是上述值，必须按本机配置调整。执行成功后先doctor、再setup --execute、最后verify；每一步成功才继续。不要重复运行apply或setup。

```powershell
cd E:\hede\backend
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin doctor
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin setup --execute
.\.venv-mcp\Scripts\python.exe -m readonly_mcp.admin verify
```

需要回滚时：先停止MCP并阻止自动重启，确认其3个账号没有连接，再使用同一psql命令把末尾文件替换为 `rollback.sql`。回滚恢复PUBLIC权限会让现有MCP账号再次继承该授权，因此不得在MCP仍对员工提供服务时操作；回滚后保持MCP关闭，另行处理。

PostgreSQL语义参考：官方18版文档的Privileges、CREATE FUNCTION、REVOKE与pg_trgm章节；本报告的对象数量、ACL、调用关系和演练结果以本次本地只读检查及独立库测试为依据。
