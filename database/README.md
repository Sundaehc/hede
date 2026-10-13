# 完整数据库结构 SQL

## 文件

- `schema.sql`：从当前项目配置的 PostgreSQL 数据库 `commodity_department` 实际导出的完整结构，导出日期 2026-10-13。
- `schema-manifest.json`：源库版本、对象清单、文件大小和 SHA-256，以及隔离恢复验证结果。

本文件针对主 PostgreSQL 数据库，不是服务器 `/opt/image-product-api/data/products.sqlite3` 的独立 SQLite 商品库。

## 包含范围

包含 `public`、`mcp_private`、`mcp_readonly` 三个 schema 的表、分区、字段、默认值、序列、索引、主键、唯一约束、外键、检查约束、视图、函数、触发器及注释。

- 普通表及分区子表：112 张。
- 分区父表：8 张，总计 120 张表。
- 视图：67 个。
- 索引：505 个普通索引、20 个分区父索引，包含约束自动创建的索引。
- 序列：94 个，包含 identity 列关联序列。
- 自定义函数：6 个。
- 已包含本次经营历程分页优化新增的两个部分索引。

由 `pg_dump --schema-only --no-owner --no-privileges --no-tablespaces` 导出，不包含业务记录、登录账号数据、API 密钥记录、原库所有者和角色授权，也不保留源服务器冷归档表空间分配。新环境需另行配置最小权限和归档表空间。库名和表空间等服务器级对象不在文件中。

## 导入到新库

使用 PostgreSQL 18 和配套 `psql`；目标环境需要提供 `pg_trgm` 扩展。导入账号须有创建相关对象及扩展的权限。`schema.sql` 含 `psql` 元命令，建议使用 `psql` 导入，不要直接交给只支持普通 SQL 的执行器。

仅对新建空库执行，不要导入现有业务库。以下命令中的连接地址、用户和目标库请按目标环境调整，密码使用交互提示，不要写入命令或提交到 Git：

```bash
createdb -h 127.0.0.1 -p 5432 -U postgres -T template0 commodity_department_new
psql -X -h 127.0.0.1 -p 5432 -U postgres -d commodity_department_new -v ON_ERROR_STOP=1 --single-transaction -f database/schema.sql
```

执行前确认目标库为空且确为新库。此文件不含 `DROP` 清库语句，不能作为覆盖已有库的升级脚本；结构变更仍应使用审核后的迁移。导入后业务表为空，包括鉴权表、MCP token 表和 `alembic_version`；不是数据备份，不会自动还原管理员、权限、商品或任务状态。

源库记录的 Alembic 版本为 `20260611_0023`，但实际结构包含后续变更；本文件按实际结构导出，不根据该版本拼接。不要直接将新库 `stamp head` 或盲目运行历史迁移，应先核对迁移版本与实际结构。

## 验证结果

已在独立临时 PostgreSQL 18.3 实例中，用 `ON_ERROR_STOP=1` 和单事务导入成功：

- 806 个关系对象的 schema、名称和类型与源库清单一致。
- 120 张表均为空，未导出业务数据。
- 6 个自定义函数恢复成功。
- 验证结束已停止临时实例，未启动或重启应用后端。

## 后续重新导出

结构发生变更后应重新导出，先使用新的文件名，避免覆盖这次验证过的文件：

```bash
pg_dump -h 127.0.0.1 -p 5432 -U postgres -d commodity_department --schema-only --format=plain --no-owner --no-privileges --no-tablespaces --encoding=UTF8 --lock-wait-timeout=5s --file=database/schema-new.sql
```

上述参数以当前项目的导出范围为准；`--no-privileges` 不等于完整的账号权限备份。重新导出后需再次核对对象清单、版本和恢复结果。
