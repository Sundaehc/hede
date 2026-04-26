# 商品管理页设计

## 目标

提供一个基于 shadcn 的商品管理页，用来查看和维护 PostgreSQL 中的四张商品表，并支持按原始货号搜索、增删改查，以及按品牌规则自动补全图片路径。

## 范围

本次范围包含两部分：

1. `frontend/` 中的管理页面与前端数据交互代码
2. `backend/` 中为该页面提供的轻量 API 层

约束：所有前端代码都放在 `frontend/` 中，不在仓库根目录或 `backend/` 中放置任何前端实现。

## 当前项目边界

### 前端

当前前端还是最小脚手架：

- `frontend/app/page.tsx` 目前只是占位页
- `frontend/app/layout.tsx` 已接入主题
- `frontend/components.json` 已配置 shadcn 别名与样式基础
- `frontend/app/globals.css` 已具备 shadcn/tailwind 主题变量

### 后端

当前后端已有可复用的数据边界：

- `backend/domain/sources.py` 定义了四个品牌键与列白名单
- `backend/domain/schema.py` 定义了四张商品表结构
- `backend/storage/db.py` 已有数据库连接与基础操作入口
- `backend/config.py` 已有数据库和共享目录配置

当前后端没有 Web API，因此前端暂时不能直接查询或修改数据。

## 设计决策

### 1. 前端只负责界面和交互

前端页面位于 `frontend/`，负责：

- 切换品牌 tab
- 通过原始货号搜索
- 展示列表与分页
- 打开新增/编辑弹窗
- 调用图片查找接口并展示提示
- 删除确认与刷新

前端不直接连接 PostgreSQL，也不直接访问共享目录。

### 2. 后端提供轻量 REST API

后端新增一个轻量 API 层，负责：

- 查询四张商品表
- 新增、更新、删除商品记录
- 根据品牌和货号标识查找共享目录中的图片
- 统一做表名映射、字段白名单控制和数据落库

这样可以复用现有 Python 配置和共享目录访问能力，避免在 TypeScript 中重复维护数据库和文件系统逻辑。

### 3. 品牌和表的映射保持与导入器一致

内部统一沿用 `backend/domain/sources.py` 中的品牌键：

- `qbd_mens`
- `qbd_womens`
- `yandou`
- `yiban`

前端 tab 文案与内部键分离：界面显示中文名称，接口传递稳定的内部键。

## 页面信息架构

管理页使用单页布局，直接替换 `frontend/app/page.tsx` 的占位内容。

### 顶部工具区

- 页面标题：商品管理
- 刷新按钮
- 新增商品按钮

### 搜索区

- 一个原始货号搜索框
- 一个搜索按钮
- 一个清空按钮

搜索始终作用于当前选中的品牌 tab，避免一次查询跨四张表混合返回。

### 品牌 Tab 区

四个 tab：

1. 千百度男鞋
2. 千百度女鞋
3. 烟斗
4. 伊伴

切换 tab 时重置页码，保留当前搜索词。

### 列表区

每个 tab 中展示一个数据表格，默认列：

- 图片
- 货号
- 原始货号
- 颜色
- 年份
- 季节分类
- 成本
- 鞋头
- 执行标准
- 首单时间
- 操作

操作列包含：

- 编辑
- 删除

图片列优先显示路径文本；如果路径可直接访问，再补充缩略展示，但这不是首版必需项。

### 分页区

列表底部显示：

- 当前页
- 总数
- 上一页 / 下一页
- 每页条数（首版可固定为 20）

## 新增与编辑交互

新增和编辑共用一个 Dialog 表单组件。

### 新增流程

1. 点击“新增商品”
2. 打开 Dialog
3. 先选择目标表/品牌
4. 填写货号、原始货号及其他字段
5. 触发图片查找
6. 自动回填 `image_path` 或显示未找到提示
7. 保存成功后关闭弹窗并刷新当前 tab 列表

### 编辑流程

1. 在当前 tab 的某条记录点击“编辑”
2. 打开同一个 Dialog
3. 目标表默认锁定为当前记录所在品牌
4. 修改字段
5. 如货号或原始货号变化，可重新触发图片查找
6. 保存成功后刷新当前列表

### 图片自动补全规则

- 后端接口接收 `brand`、`original_sku`、`sku` 三个字段
- 图片查找时优先使用 `original_sku`
- 若 `original_sku` 为空，再回退使用 `sku`
- 两者都为空时直接返回未找到，不访问共享目录
- 匹配逻辑复用当前导入器的品牌目录映射和 `ImageMatcher` 的精确文件名 stem 匹配
- 找到则回填 `image_path`
- 未找到则返回 warning，但不阻止保存

## 删除交互

删除必须走二次确认。

确认内容至少包含：

- 当前品牌
- 原始货号
- 货号

删除成功后：

- 若当前页仍有数据，留在原页刷新
- 若删除后当前页为空且不是第一页，回退到上一页

## 前端组件拆分

前端代码全部放在 `frontend/` 下，建议结构如下：

- `frontend/app/page.tsx`
  - 页面入口，负责装配整个管理页
- `frontend/components/product-admin/product-admin-page.tsx`
  - 页面主容器与状态编排
- `frontend/components/product-admin/product-toolbar.tsx`
  - 标题、刷新、新增按钮、搜索框
- `frontend/components/product-admin/product-tabs.tsx`
  - 品牌 tab 切换
- `frontend/components/product-admin/product-table.tsx`
  - 列表展示与操作按钮
- `frontend/components/product-admin/product-form-dialog.tsx`
  - 新增/编辑弹窗
- `frontend/components/product-admin/delete-product-dialog.tsx`
  - 删除确认框
- `frontend/components/product-admin/image-lookup-status.tsx`
  - 图片匹配结果提示
- `frontend/lib/api.ts`
  - 统一封装前端到后端的请求
- `frontend/lib/brands.ts`
  - 品牌键和中文文案映射
- `frontend/lib/types.ts`
  - 前端类型定义

首版不引入额外状态库，使用 React state 和组件内请求编排即可。

## 前端状态模型

页面主状态包括：

- `activeBrand`
- `searchQuery`
- `page`
- `pageSize`
- `items`
- `total`
- `loading`
- `error`
- `isFormOpen`
- `editingProduct`
- `isDeleteOpen`
- `deletingProduct`
- `imageLookupState`

目标是让一个页面组件掌握查询状态，再把弹窗和表格拆成纯展示/受控交互组件。

## 前后端联通方式

开发阶段默认采用前后端分端口运行：

- `frontend/` 运行 Next.js 开发服务
- `backend/` 运行 FastAPI 服务

前端通过统一的 `frontend/lib/api.ts` 读取后端基地址，例如 `NEXT_PUBLIC_API_BASE_URL`。

首版不把 API 放进 `frontend/app/api`，避免在 Next.js 中重复实现数据库访问和共享目录访问逻辑。若开发体验需要，可在后续增加 Next.js rewrite/proxy，但不属于首版必要范围。

## 后端 API 设计

建议在 `backend/` 中新增独立 API 模块，使用 FastAPI 提供 JSON 接口。

### 路由

#### `GET /products`

查询当前品牌下的商品列表。

参数：

- `brand`: 品牌键，必填
- `query`: 原始货号搜索词，可选
- `page`: 页码，默认 1
- `page_size`: 每页数量，默认 20

返回：

- `items`
- `total`
- `page`
- `page_size`

其中 `items` 至少包含列表展示所需字段和 `id`、`brand`，以便前端直接驱动表格与编辑弹窗。

#### `GET /products/{brand}/{id}`

查询单条商品记录详情。

#### `POST /products`

新增商品。

请求体包含：

- `brand`
- `payload`

成功返回：

- `item`
- `message`

#### `PUT /products/{brand}/{id}`

更新商品。

成功返回：

- `item`
- `message`

#### `DELETE /products/{brand}/{id}`

删除商品。

成功返回：

- `message`

#### `POST /images/lookup`

根据品牌与货号标识查找图片路径。

请求体：

- `brand`
- `original_sku`
- `sku`

返回：

- `found`
- `image_path`
- `matched_by`（`original_sku` / `sku` / `none`）
- `message`

## 后端实现边界

为了避免改坏现有导入器，API 层应建立在新增模块上，不直接改写导入流程。

当前 `backend/main.py` 仍是 CLI 入口，因此首版需要把命令行入口与 Web 入口分开：

- 保留现有 `backend/main.py` / `cli.py` 给导入器使用
- 新增独立的 `backend/api_main.py` 或等价入口给 FastAPI 使用

建议新增：

- `backend/api/app.py`
- `backend/api/schemas.py`
- `backend/api/routes/products.py`
- `backend/api/routes/images.py`
- `backend/storage/product_repository.py`
- `backend/api_main.py`（Web 服务启动入口）

并补充后端 Web 运行依赖：

- `fastapi`
- `uvicorn`

其中：

- API 层只负责请求解析和响应格式
- repository 层负责表映射、分页查询、CRUD
- 图片查找继续复用当前图片目录配置和匹配器逻辑

## 数据规则

### 查询

- 只搜索当前选中品牌表
- 搜索字段为 `original_sku`
- 首版支持包含匹配即可

### 写入

- 写入字段以 `backend/domain/sources.py` 的 canonical columns 为准
- 首版表单允许编辑的字段固定为：
  - `image_path`
  - `sku`
  - `original_sku`
  - `group_name`
  - `cost`
  - `factory_sku`
  - `color`
  - `season_category`
  - `year`
  - `upper_material`
  - `lining_material`
  - `outsole_material`
  - `insole_material`
  - `execution_standard`
  - `heel_height`
  - `shoe_width`
  - `shoe_length`
  - `shaft_circumference`
  - `shaft_height`
  - `internal_height_increase`
  - `internal_height_note`
  - `upper_height`
  - `toe_shape`
  - `closure_type`
  - `shoe_box_spec`
  - `first_order_time`
- 非法字段不入库
- `id` 不允许前端编辑
- `source_workbook`、`source_sheet`、`source_row_number`、`raw_payload` 不在前端表单中暴露
- 新增记录时，后端统一写入人工维护元数据：
  - `source_workbook = "manual_admin"`
  - `source_sheet = brand`
  - `source_row_number = "manual"`
  - `raw_payload` 保存一次经归一化后的表单提交快照
- 编辑记录时：
  - 业务字段按最新提交覆盖
  - `raw_payload` 更新为最新归一化快照
  - 若原记录来源于 Excel 导入，则保留原有 `source_workbook`、`source_sheet`、`source_row_number`
  - 若原记录来源于人工新增，则继续保留人工元数据

### 时间与空值

- `cost` 在后端按现有归一化逻辑转为数值，非法值写为 `NULL`
- `year` 在前端按文本输入，后端按字符串保存
- `first_order_time` 在前后端都按 `YYYY-MM-DD` 处理，提交空值时写为 `NULL`
- 空字符串在后端归一为 `NULL`
- 未匹配到图片时，`image_path` 允许为空

## 错误处理

### 前端

- 列表查询失败：表格区域展示错误提示和重试按钮
- 保存失败：Dialog 内展示错误信息，不关闭弹窗
- 图片未匹配：展示 warning，不阻塞保存
- 删除失败：toast 或行内提示失败信息

### 后端

- 非法品牌：返回 400
- 记录不存在：返回 404
- 数据校验失败：返回 422
- 数据库异常：返回 500，并记录日志
- 共享目录不可访问：图片查找接口返回失败信息，不影响商品 CRUD

## 安全与约束

- API 只接受白名单字段，避免任意列写入
- 所有 SQL 操作通过 SQLAlchemy 构造，不拼接原始 SQL
- 品牌键通过固定映射转表，不接受任意表名输入
- 文件路径只通过后端既有配置的品牌目录查找，不接受前端传入任意目录

## 首版不做的内容

本次不包含：

- 跨品牌混合搜索
- 批量导入/批量删除
- 列排序、自定义列配置
- 登录鉴权
- 图片上传
- 表格虚拟滚动
- 自动轮询刷新

## 验证方案

### 后端

- CRUD API 单元测试
- 图片查找接口测试
- 品牌到表名映射测试
- 非法字段过滤测试

### 前端

- tab 切换后查询正确品牌
- 原始货号搜索只作用于当前品牌
- 新增商品时必须先选目标品牌
- 图片查找成功时自动回填路径
- 图片查找失败时显示 warning 且允许保存
- 编辑和删除后列表正确刷新

### 联调

至少验证以下场景：

1. 千百度男鞋 tab 查询并搜索一个已存在原始货号
2. 在任一 tab 新增一条记录并成功保存
3. 编辑一条记录并重新触发图片查找
4. 用一个无图货号测试 warning 提示
5. 删除一条刚新增的记录

## 推荐实施顺序

1. 在 `backend/` 增加 API 层和 repository
2. 先完成列表查询、单条查询、图片查找
3. 再完成新增、编辑、删除接口
4. 在 `frontend/` 完成页面骨架、tab、搜索、表格
5. 接入新增/编辑 Dialog
6. 接入删除确认
7. 完成联调与回归测试

## 设计结论

采用“`frontend/` 中实现完整管理页 + `backend/` 中补充轻量 API”的方案。

这样可以满足：

- 前端代码全部位于 `frontend/`
- 复用现有 Python 数据库与共享目录能力
- 不破坏当前 Excel 导入器
- 后续可继续扩展更多筛选条件和字段展示