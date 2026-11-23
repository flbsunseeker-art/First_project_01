# StockPilot V1.5

StockPilot 是一个本地优先的 A 股 / 港股 / 美股 / 场外基金收益追踪工具。
项目使用人民币统一估值，不连接券商，也不维护现金、手续费或分红。

当前目标架构已经调整为：

```text
Frontend: Next.js + React + TypeScript
Backend: FastAPI + Python
Database: SQLite first, PostgreSQL ready
```

旧 Streamlit 原型已经移出本项目目录，仅作为本地备份参考；当前仓库只保留新项目实现。

## 核心能力

- 查看买卖日期、股数与成交价，以及估值和同步状态
- 独立管理场外基金份额、总成本、最新净值和净值日期
- 按已发布净值自动补写固定每日定投，并保证重复刷新不重复记账
- 使用移动加权平均法推导持仓成本和已实现盈亏
- 展示股票总市值、当前持仓、行业分布和市场分布
- 自动补齐历史收盘价、汇率和每日组合快照
- 总资产市值趋势、持仓与指数收益对比、收益日历
- 阅读按周归档的组合诊断、持有判断与调整建议

每日盈亏会剔除当日买卖产生的本金变化：

```text
每日盈亏 = 当日资产总市值 - 上一估值日资产总市值
          - 当日买入金额 - 新增资产基线金额 + 当日卖出金额
```

## 本地启动

在 macOS Finder 里双击项目根目录的 `start.command`。脚本会启动 FastAPI 和 Next.js，等页面就绪后打开默认浏览器。如果服务已经在运行，会直接打开页面。

后端每次冷启动会在后台刷新一次持仓行情、汇率和已发布的基金净值。总览先展示最近完整快照，更新后显示实际行情日期。部分来源暂不可用时，可以在总览查看详情并手动刷新。

也可以在终端运行 `./start.command`。默认页面地址为 [http://127.0.0.1:3000](http://127.0.0.1:3000)，后端端口为 8000。脚本启动的服务会随启动窗口关闭，也可以按 Ctrl+C 停止。

启动器运行正式前端，首次运行或前端源文件有变化时会重新构建。开发时可用 `STOCKPILOT_DEV=1 ./start.command` 开启热重载。

如端口被占用，可以临时指定端口：

```bash
STOCKPILOT_API_PORT=8002 STOCKPILOT_WEB_PORT=3002 ./start.command
```

## 在另一台电脑同步运行

从 GitHub 克隆仓库：

```bash
git clone git@github.com:flbsunseeker-art/First_project_01.git
cd First_project_01
```

安装后端依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

安装前端依赖：

```bash
cd apps/web
corepack enable
pnpm install
cd ../..
```

如果 `corepack` 不可用，可以先安装 pnpm：

```bash
npm install -g pnpm
```

启动应用：

```bash
./start.command
```

然后访问：

```text
http://127.0.0.1:3000
```

如果公司电脑不能使用 SSH clone，也可以把远端地址换成 HTTPS。

```bash
git clone https://github.com/flbsunseeker-art/First_project_01.git
```

### Backend

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn apps.api.main:app --reload --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### Frontend

前端位于 `apps/web`。推荐使用 `pnpm`。

```bash
cd apps/web
pnpm install
pnpm run dev
```

默认访问：

```text
http://localhost:3000
```

当前仓库已在 `apps/web/package.json` 中配置 `NEXT_TEST_WASM_DIR`，用于兼容
Intel macOS / Codex 环境中 Next.js 原生 SWC 二进制加载受限的问题。

## 本地数据

账本默认保存在本地 `data/portfolio.db`，诊断周报保存在 `data/portfolio.research.db`。数据库、备份、缓存、生成报告和本地环境配置均由 `.gitignore` 排除。开发测试使用虚构的持仓和交易数据。

如需在另一台电脑演示同一份真实数据，需要手动复制本机的 `data/portfolio.db` 到新电脑同路径：

```text
data/portfolio.db
```

如果不复制数据库，应用仍可启动，但会使用新电脑本地的数据状态。

## 数据结构

- `securities`：证券基础信息和可编辑行业
- `opening_positions`：迁移得到的期初持仓
- `fund_investment_plans` / `fund_plan_executions`：固定定投及幂等执行记录
- `trades`：手工买卖流水
- `market_prices` / `exchange_rates`：历史行情与汇率缓存
- `daily_position_snapshots`：每日证券级估值
- `daily_portfolio_snapshots`：每日组合级收益
- `sync_runs`：历史补算状态

如果检测到旧版根目录 `portfolio.db`，系统会在首次初始化时复制到新路径并保留备份。除非你手动复制数据库，否则 GitHub 同步只同步应用代码，不同步投资数据。

## 验证命令

后端核心测试：

```bash
python3 -m pytest tests/test_portfolio_storage.py
```

前端类型检查和构建：

```bash
cd apps/web
pnpm run typecheck
pnpm run build
```

API smoke：

```bash
python3 -m uvicorn apps.api.main:app --port 8000
curl http://127.0.0.1:8000/api/v1/health
```
