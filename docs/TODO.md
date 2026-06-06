# StockPilot TODO

## 0. 当前目标

按新的目标架构推进 StockPilot：

```text
Next.js / React frontend
FastAPI backend
SQLite first, PostgreSQL ready
```

原则：

- 先保核算正确，再做页面完整，最后做视觉精修。
- 每个阶段都保持本地可运行、可测试。
- 任务拆解结合当前已有实现，优先迁移、复用和加固，不从零重写。
- 稳定 checkpoint 做本地 Git commit，方便回溯和回滚。
- milestone 完成并验证通过后，由 Codex 判断是否同步远端；开发小步中不频繁 push。

## 0.1 Git 节奏

建议节奏：

- 文档和架构对齐完成：本地 commit。
- 每个 milestone 完成：本地 commit。
- milestone 验收通过且工作区干净：push 到远端。
- 中途实验性代码：不急着 commit，先跑通再整理。

push 判断条件：

- 当前 milestone 的验收项通过；
- 相关测试通过；
- `git status` 中没有不应提交的数据库、备份、缓存或临时文件；
- commit 范围清楚，能解释“这次为什么值得同步”。

默认远端：

- `origin`
- 当前分支优先保持用户所在分支，除非明确需要新建开发分支。

## 1. Milestone 1：项目骨架重组

目标：建立前后端分离的基础工程，不急着迁移所有功能。

复用策略：

- 保留现有 `ledger.py`、`valuation.py`、`market_data.py`、`storage.py` 作为迁移来源。
- 不在骨架阶段重写核算逻辑。
- 先把 FastAPI 和 Next.js 跑通，再逐步搬迁现有模块。

任务：

- [ ] 创建 `apps/api` FastAPI 后端目录。
- [ ] 创建 `apps/web` Next.js 前端目录。
- [ ] 建立共享运行说明：后端端口、前端端口、环境变量。
- [ ] 将 SQLite 默认路径迁移到 `data/portfolio.db`。
- [ ] 保留现有 `portfolio.db` 的备份和迁移路径。
- [ ] 更新 `.gitignore`，确保数据库、备份、缓存不入库。
- [ ] 保留旧 Streamlit 入口作为临时参考，不再新增功能。

验收：

- [ ] `apps/api` 可启动并返回 health check。
- [ ] `apps/web` 可启动并访问首页占位页。
- [ ] 现有测试仍可运行。

## 2. Milestone 2：后端领域服务迁移

目标：把现有账本、估值、行情和存储逻辑迁移到 FastAPI 后端内部。

任务：

- [ ] 迁移 `storage.py` 到 `apps/api/repositories` 或 `apps/api/infrastructure`。
- [ ] 迁移 `ledger.py` 到 `apps/api/domain` / `apps/api/services`。
- [ ] 迁移 `valuation.py` 到 `apps/api/services`。
- [ ] 迁移 `market_data.py` 和 `fetcher.py` 到 `apps/api/adapters`。
- [ ] 迁移 `report.py` 到 `apps/api/services`。
- [ ] 保持核心计算模块不依赖 FastAPI request/response。
- [ ] 补齐后端配置：数据库路径、离线模式、行情源开关。

验收：

- [ ] 移动平均成本测试通过。
- [ ] 每日收益现金流调整测试通过。
- [ ] 行业分布一致性测试通过。
- [ ] 手动行业修改持久化测试通过。

## 3. Milestone 3：数据库 schema v3

目标：补齐 PRD 明确的数据字段和迁移能力。

任务：

- [ ] 为 `trades` 增加 `reason_category` 字段。
- [ ] 为 `trades` 增加 `note` 字段。
- [ ] 建立 schema migration 机制。
- [ ] 迁移现有 v2 数据到 v3。
- [ ] 迁移前自动备份数据库。
- [ ] 明确 `metadata.schema_version = 3`。
- [ ] 为未来 PostgreSQL 避免使用难迁移的 SQLite 专有写法。

验收：

- [ ] 旧数据库可以无损迁移。
- [ ] 现有证券、期初持仓、行业、快照不丢失。
- [ ] 交易理由和备注可以保存、读取、编辑。

## 4. Milestone 4：核心 API

目标：前端不直接访问数据库，统一通过 FastAPI 读取和写入。

任务：

- [ ] `GET /api/v1/health`
- [ ] `GET /api/v1/overview`
- [ ] `GET /api/v1/holdings`
- [ ] `GET /api/v1/holdings/allocation/industry`
- [ ] `GET /api/v1/holdings/allocation/market`
- [ ] `PATCH /api/v1/securities/{id}/industry`
- [ ] `GET /api/v1/trades`
- [ ] `POST /api/v1/trades`
- [ ] `PATCH /api/v1/trades/{id}`
- [ ] `DELETE /api/v1/trades/{id}`
- [ ] `GET /api/v1/analytics/daily-returns`
- [ ] `GET /api/v1/analytics/snapshots/{date}`
- [ ] `GET /api/v1/analytics/value-trend`
- [ ] `GET /api/v1/data/status`
- [ ] `POST /api/v1/data/backfill`
- [ ] `POST /api/v1/data/backup`
- [ ] `GET /api/v1/report/html`

验收：

- [ ] API 返回字段与 PRD 指标一致。
- [ ] 交易新增、修改、删除后会触发后续快照重算。
- [ ] 缺行情或缺汇率时 API 返回明确状态。
- [ ] OpenAPI 文档可访问。

## 5. Milestone 5：Next.js 前端基础

目标：先搭起可用页面壳和统一视觉基线。

任务：

- [ ] 创建 Next.js App Router 项目。
- [ ] 建立暗色主题 token。
- [ ] 建立响应式 App shell。
- [ ] 建立桌面端导航。
- [ ] 建立移动端底部 Tab。
- [ ] 封装 API client。
- [ ] 封装基础 UI 组件：Card、Badge、Button、Table、Dialog、Form。
- [ ] 建立红涨绿跌格式化工具。

验收：

- [ ] Web 端和手机宽度下页面可正常阅读。
- [ ] 基础主题与 `DESIGN.md` 一致。
- [ ] 前端不包含直接数据库访问。

## 6. Milestone 6：核心页面

目标：完成 MVP 用户每天真正会用的页面。

任务：

- [ ] 总览页：KPI、数据状态、总市值趋势、每日收益概览。
- [ ] 持仓页：持仓表、移动端持仓卡片、行业分布、市场分布。
- [ ] 交易页：新增交易、编辑交易、删除交易、交易流水。
- [ ] 收益分析页：收益日历、每日收益柱状图、总市值趋势。
- [ ] 设置与数据页：证券行业编辑、同步状态、备份、HTML 报告。

验收：

- [ ] 总览、持仓、行业分布、收益分析使用同一套后端结果。
- [ ] 收益为红、亏损为绿。
- [ ] 移动端不依赖宽表格完成核心查看。
- [ ] 数据异常状态能被明确感知。

## 7. Milestone 7：导入导出与报告

目标：保证本地数据安全和可迁移。

任务：

- [ ] 交易记录 CSV 导入。
- [ ] 交易记录 CSV 导出。
- [ ] 数据库手动备份。
- [ ] HTML 报告导出 API。
- [ ] HTML 报告补齐总成本、收益率、今日收益、行业/市场分布。

验收：

- [ ] CSV 导入失败能指出失败行和原因。
- [ ] 备份文件保存在本地。
- [ ] HTML 报告和应用视觉口径一致。

## 8. Milestone 8：旧实现收口

目标：完成从原型到目标架构的切换。

任务：

- [ ] 确认 Next.js + FastAPI 覆盖现有 Streamlit 核心能力。
- [ ] 标记 Streamlit `app.py` 为 deprecated 或移入 legacy。
- [ ] 清理 `portfolio.py` 旧兼容层。
- [ ] 更新 README 启动方式。
- [ ] 更新测试命令。

验收：

- [ ] 新架构本地启动路径清晰。
- [ ] 旧入口不再作为主使用路径。
- [ ] 文档与代码结构一致。

## 9. 当前优先级

下一步从 **Milestone 1** 开始：

1. 搭建 `apps/api` FastAPI health check。
2. 搭建 `apps/web` Next.js 首页占位。
3. 更新本地启动说明。
4. 跑通最小前后端本地开发链路。
