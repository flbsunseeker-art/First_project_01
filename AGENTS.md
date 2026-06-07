# StockPilot Agent Guide

## Communication

- 使用中文沟通。
- 回复保持简洁、聚焦，避免重复和过度展开。
- 重要设计或架构选择需要说明理由。

## Product Direction

- 产品名：StockPilot。
- 目标：本地优先的多市场股票持仓与收益管理工具。
- 支持范围：A 股、港股、美股。
- 不对接券商账户。
- 不维护现金、手续费、分红、做空、融资、期权或其他资产。
- 用户手动维护证券、期初持仓和交易。
- 系统自动推导持仓、成本、收益、行业分布、市场分布和历史快照。

## Target Architecture

- Frontend：Next.js + React + TypeScript。
- Backend：FastAPI + Python。
- Database：SQLite first，PostgreSQL ready。
- 旧 Streamlit 原型已移出当前项目目录，仅作为本地备份参考；当前仓库只维护新架构。

## Engineering Principles

- 账本为真相源：当前持仓必须由期初持仓和交易流水推导。
- 核算优先：先保证 Decimal 计算、移动平均成本、每日收益和历史补算正确。
- 前后端分离：前端不直接访问数据库。
- 数据本地优先：持仓、交易、成本和收益默认保存在本地。
- 缺行情或汇率时必须展示异常状态，不生成伪准确收益。
- 行业属于证券基础信息，手动修改后不得被自动识别覆盖。
- 页面必须共享同一套后端核算结果。

## Data Rules

- 盈利 / 上涨：红色。
- 亏损 / 下跌：绿色。
- 默认报告币种：CNY。
- 金额、价格、汇率和股数使用 `Decimal` 计算。
- SQLite 中精确数值优先以文本保存，避免浮点误差。
- 修改或删除历史交易后，必须从最早受影响日期重算后续快照。

## Workflow

- 需求来源以 `docs/PRD.md` 为准。
- 视觉和响应式方向以 `docs/DESIGN.md` 为准。
- 技术架构以 `docs/ARCHITECTURE.md` 为准。
- 开发任务以 `docs/TODO.md` 为准。
- 每个阶段尽量保持本地可运行、可测试。
- 任务拆解必须结合当前已有实现，优先迁移和复用已验证的账本、估值、行情、报告和测试逻辑，不从零重写。
- 开发粒度以可回滚、可验收的小步任务为准。
- 关键本地变更应通过 Git commit 形成清晰 checkpoint，方便回溯和回滚。
- 远端同步以 milestone 为单位，由 Codex 在 milestone 验收通过后判断是否 push；小步开发期间不频繁 push。

## Local Development

- 不要把本地数据库、备份、缓存、生成文件提交到 Git。
- 迁移数据库前必须创建备份。
- 对既有用户数据做变更时要谨慎，避免破坏当前 `portfolio.db`。
- 修改数据库 schema 时同步更新迁移逻辑和测试。

## Testing

- 后端核心逻辑必须有单元测试。
- 至少覆盖：
  - 多次买入移动平均成本；
  - 部分卖出已实现盈亏；
  - 超额卖出拒绝；
  - 买入 / 卖出现金流不误算为市场收益；
  - 行业分布之和等于总市值；
  - 历史交易修改后快照重算；
  - 行情 / 汇率缺失状态。

## Git

- 默认在本地开发，优先保持工作区可测试、可回滚。
- 每个稳定 checkpoint 可以创建本地 commit，commit 前需确认变更范围并运行相关验证。
- Commit message 应简洁描述业务或架构阶段，例如 `docs: align target architecture`、`api: add health endpoint`。
- 不为零散半成品频繁提交；不把数据库、备份、缓存或临时文件提交。
- 每个大 milestone 完成且验证通过后，可以由 Codex 判断是否 push 到远端仓库。
- push 前需确认当前分支、远端和待推送 commit 范围。
- 如果用户明确要求暂不同步远端，则只保留本地 commit。
- 面试演示阶段需要保证 GitHub 远端可拉取完整应用代码；本地 `data/portfolio.db` 仍不随 Git 同步。
