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

## 0.1 验收精简原则

为节约开发 token 和本地执行成本，后续 milestone 不重复跑完整 PRD 验收，只做与本阶段改动直接相关的验证：

- 文档或配置变更：检查格式、路径和启动说明是否一致。
- 后端领域逻辑变更：跑对应单元测试和一次 API smoke test。
- 数据库迁移变更：跑迁移备份、schema version、旧数据保留的最小验证。
- 前端页面变更：跑 typecheck/build，并在桌面和移动宽度各做一次关键页面 smoke。
- 跨模块重构：优先验证公开接口和现有测试，不逐文件做机械确认。

完整回归只在以下情况执行：

- milestone 收口准备 push；
- 数据模型、核算公式或迁移逻辑发生变化；
- 用户反馈具体数值异常；
- 从旧 Streamlit 入口正式切换到新架构。

## 0.2 Git 节奏

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

- [x] 创建 `apps/api` FastAPI 后端目录。
- [x] 创建 `apps/web` Next.js 前端目录。
- [x] 建立共享运行说明：后端端口、前端端口、环境变量。
- [x] 将 SQLite 默认路径迁移到 `data/portfolio.db`。
- [x] 保留现有 `portfolio.db` 的备份和迁移路径。
- [x] 更新 `.gitignore`，确保数据库、备份、缓存不入库。
- [x] 保留旧 Streamlit 入口作为临时参考，不再新增功能。

最小验收：

- [x] `apps/api` 可启动并返回 health check。
- [x] `apps/web` 可启动并访问首页占位页。
- [x] 现有测试仍可运行。

备注：

- 当前本机 Codex 环境有 Node，但没有系统级 `npm` / `pnpm` / `yarn` / `corepack`。
- 已使用项目本地 `.tools/pnpm` 安装前端依赖并完成 Next.js 首页验证。

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

最小验收：

- [ ] 现有账本、估值、行情、报告测试在新路径下通过。
- [ ] FastAPI 可以调用迁移后的服务返回 health/overview smoke 结果。
- [ ] 核心计算模块仍不依赖 FastAPI。

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

最小验收：

- [ ] 迁移前会生成数据库备份。
- [ ] 旧数据迁移后证券、期初持仓、行业、快照数量一致。
- [ ] `reason_category` 和 `note` 可以保存、读取。

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

最小验收：

- [ ] OpenAPI 文档可访问。
- [ ] 总览、持仓、交易、收益、数据状态各有一个 smoke 测试。
- [ ] 交易写入接口能触发重算入口。

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

最小验收：

- [ ] `pnpm typecheck` 和 `pnpm build` 通过。
- [ ] 桌面和移动宽度下 App shell 可读。
- [ ] 前端只通过 API client 访问后端。

## 6. Milestone 6：核心页面

目标：完成 MVP 用户每天真正会用的页面。

任务：

- [ ] 总览页：KPI、数据状态、总市值趋势、每日收益概览。
- [ ] 持仓页：持仓表、移动端持仓卡片、行业分布、市场分布。
- [ ] 交易页：新增交易、编辑交易、删除交易、交易流水。
- [ ] 收益分析页：收益日历、每日收益柱状图、总市值趋势。
- [ ] 设置与数据页：证券行业编辑、同步状态、备份、HTML 报告。

最小验收：

- [ ] 每个核心页面可打开并展示后端数据。
- [ ] 盈利为红、亏损为绿。
- [ ] 移动端能完成总览、持仓、收益查看。

## 7. Milestone 7：导入导出与报告

目标：保证本地数据安全和可迁移。

任务：

- [ ] 交易记录 CSV 导入。
- [ ] 交易记录 CSV 导出。
- [ ] 数据库手动备份。
- [ ] HTML 报告导出 API。
- [ ] HTML 报告补齐总成本、收益率、今日收益、行业/市场分布。

最小验收：

- [ ] CSV 导入导出可完成一轮往返。
- [ ] 备份文件保存在本地且不入 Git。
- [ ] HTML 报告包含总成本、收益率、行业/市场分布。

## 8. Milestone 8：旧实现收口

目标：完成从原型到目标架构的切换。

任务：

- [ ] 确认 Next.js + FastAPI 覆盖现有 Streamlit 核心能力。
- [ ] 标记 Streamlit `app.py` 为 deprecated 或移入 legacy。
- [ ] 清理 `portfolio.py` 旧兼容层。
- [ ] 更新 README 启动方式。
- [ ] 更新测试命令。

最小验收：

- [ ] 新架构本地启动路径清晰。
- [ ] 旧入口不再作为主使用路径。
- [ ] 文档与代码结构一致。

## 9. 轻量回归清单

仅在 milestone 收口、核算逻辑变化或准备远端同步前执行：

- [ ] 多次买入移动平均成本正确。
- [ ] 部分卖出已实现盈亏和剩余成本正确。
- [ ] 超额卖出被拒绝。
- [ ] 买入 / 卖出现金流不误算为每日市场收益。
- [ ] 行业分布之和等于总市值。
- [ ] 手动行业修改能持久保存。
- [ ] 缺行情或缺汇率时有明确状态。
- [ ] 总览、持仓、行业分布、收益分析使用同一套后端结果。

## 10. 当前优先级

下一步从 **Milestone 2** 开始：

1. 结合现有实现梳理可迁移模块边界。
2. 将账本、估值、行情和存储逻辑迁移到 FastAPI 后端目录。
3. 保持核心计算模块不依赖 FastAPI。
4. 跑通迁移后的后端最小测试链路。
