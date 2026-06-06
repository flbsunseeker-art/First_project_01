# StockPilot

StockPilot 是一个本地优先、手动维护交易的 A 股 / 港股 / 美股收益追踪工具。
项目使用人民币统一估值，不连接券商，也不维护现金、手续费或分红。

当前目标架构已经调整为：

```text
Frontend: Next.js + React + TypeScript
Backend: FastAPI + Python
Database: SQLite first, PostgreSQL ready
```

旧 Streamlit 实现仅作为原型参考，后续不再作为目标产品架构扩展。

## 核心能力

- 手动记录买入和卖出的日期、股数与成交价
- 使用移动加权平均法推导持仓成本和已实现盈亏
- 展示股票总市值、当前持仓、行业分布和市场分布
- 自动补齐历史收盘价、汇率和每日组合快照
- 收益日历、股票总市值曲线、累计收益曲线和每日盈亏
- 交易 CSV 导入导出、HTML 报告和 SQLite 数据库备份

每日盈亏会剔除当日买卖产生的本金变化：

```text
每日盈亏 = 当日股票总市值 - 上一估值日股票总市值
          - 当日买入金额 + 当日卖出金额
```

## 新架构本地启动

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

前端位于 `apps/web`。当前环境需要可用的 Node 包管理器，例如 `npm`、`pnpm`
或 `yarn`。

```bash
cd apps/web
npm install
npm run dev
```

默认访问：

```text
http://localhost:3000
```

## 旧原型启动

```bash
python3 -m pip install -r requirements.txt
./start.sh
```

首次启动新版时，旧 `holdings` 数据会迁移为期初持仓，并在 `backups/`
目录创建迁移前数据库副本。迁移日是可信历史起点，迁移日前不生成收益曲线。

## 数据结构

- `securities`：证券基础信息和可编辑行业
- `opening_positions`：迁移得到的期初持仓
- `trades`：手工买卖流水
- `market_prices` / `exchange_rates`：历史行情与汇率缓存
- `daily_position_snapshots`：每日证券级估值
- `daily_portfolio_snapshots`：每日组合级收益
- `sync_runs`：历史补算状态

所有业务数据默认保存在本地 `data/portfolio.db`。如果检测到旧版根目录
`portfolio.db`，系统会在首次初始化时复制到新路径并保留备份。除非明确执行 Git 操作，否则应用
不会提交或上传任何投资数据。
