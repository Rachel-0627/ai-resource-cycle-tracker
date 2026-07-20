# AI Resource Cycle Tracker

面向 **ASX 中小盘矿业勘探股**(Explorer / Developer)的投研雷达:通过公告、资金行为、价格/成交量发现"正在形成市场共识的资源故事",给出**可解释**的 Cycle Score,记录每一次信号,并用回测验证这些信号在历史上有没有参考价值。

> ⚠️ **仅供研究参考,不构成投资建议。** 系统输出的标签固定为 High Priority / Watch Closely / Monitor / Ignore 四档,不是买卖建议;Cycle Score 衡量的是"故事共识强度",不是上涨概率。

## 架构

```
yfinance(.AX 日线/商品/基准) ──┐
ASX 公告 API(markitdigital) ──┤→ 数据层(SQLite) → 规则层(指标/分类) → 评分层(Cycle Score)
                              │                                        ↓
                              └────────────→ 信号引擎 → 信号留痕 → 回测(+5/20/60/120d, 超额 vs OZR.AX)
                                                                       ↓
                                                        日报 → Telegram 推送 / Web Dashboard
```

- **后端**: FastAPI + SQLAlchemy + SQLite(`data/tracker.db`),APScheduler 每个交易日 18:30(Australia/Sydney)自动跑全流程
- **前端**: React + Vite + TypeScript + Ant Design + ECharts(雷达排名 / 个股详情 / 信号 / 回测 / 日报 / 设置 六页)
- **AI 分析层**: MVP-1 为纯规则;`app/analysis/ai_stub.py` 预留了 `AnnouncementAnalyzer` 接口,phase-2 接入 Claude 做公告摘要/结构化提取时无需改动 pipeline

## 快速开始

```bash
# 1) 后端环境(需要 Python 3.10+;macOS/Linux 示例)
cd backend
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # 按需填 Telegram token

# 2) 初始化股票池(30 只 ASX 资源小票种子,junior 并购退市频繁,务必校验)
cd ..
backend/.venv/bin/python scripts/seed_watchlist.py
backend/.venv/bin/python scripts/validate_seed.py   # 报 DEAD 的票要替换

# 3) 首次全量跑(联网:回填约 2 年日线 + 抓公告 + 评分 + 信号 + 日报,约 2 分钟)
backend/.venv/bin/python scripts/run_pipeline.py

# 4) 历史回放(给回测页灌历史样本,一次性)
backend/.venv/bin/python scripts/replay_signals.py --days 400

# 5) 起后端
cd backend && .venv/bin/uvicorn app.main:app --port 8000

# 6) 起前端(另开终端)
cd frontend && npm install && npm run dev
# 打开 http://localhost:5173
```

Windows PowerShell 对应命令:

```powershell
# 1) 后端环境
cd backend
py -3.10 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env

# 2) 初始化股票池
cd ..
backend\.venv-win\Scripts\python.exe scripts\seed_watchlist.py
backend\.venv-win\Scripts\python.exe scripts\validate_seed.py

# 3) 首次全量跑 + 历史回放
backend\.venv-win\Scripts\python.exe scripts\run_pipeline.py
backend\.venv-win\Scripts\python.exe scripts\replay_signals.py --days 400

# 4) 起后端
cd backend
.\.venv-win\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 5) 起前端(另开 PowerShell)
cd frontend
npm install
npm run dev
```

如果前端目录是从 macOS/Linux 拷贝来的,`node_modules/.bin` 可能缺少 Windows `.cmd` 启动脚本,表现为 `tsc is not recognized`。在 Windows 下重新执行一次 `npm install` 即可重建这些脚本。

## .env 配置(backend/.env)

| 变量 | 说明 |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 填了才推送日报;不填则日报仍生成入库,只是跳过推送 |
| `EMAIL_SMTP_HOST` / `EMAIL_FROM` / `EMAIL_TO` | 填了才通过 SMTP 邮件推送日报;不填则跳过邮件推送 |
| `EMAIL_SMTP_PORT` / `EMAIL_SMTP_USERNAME` / `EMAIL_SMTP_PASSWORD` / `EMAIL_USE_TLS` | SMTP 端口、登录凭据和 TLS 开关 |
| `ENABLE_SCHEDULER` | `true` 开启每日自动 pipeline(开发时用 `--reload` 请保持 `false`,避免双跑) |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | 默认 18:30 悉尼时间(ASX 16:00 收盘后) |
| `ASX_ACCESS_TOKEN` | ASX 官网前端内嵌的公开 token,轮换失效时在此覆盖 |

权重、标签阈值、信号阈值、商品映射、回测基准存在数据库 `app_config` 表,可在**设置页**改,无需重启。

## Cycle Score(固定权重,可在设置页调)

| 子分 | 权重 | MVP-1 实现 |
|---|---|---|
| Funding | 35% | 放量(方向门槛:收涨才计;流动性地板:成交额 ≥ A$50k)+ 突破(20/60/252d 取最高档)+ 连涨 + 量能趋势 |
| Announcement | 30% | 关键词分类(11 类)× 时间衰减 × price-sensitive 加成 + 多公告 bonus;30 天无公告 = 0 |
| Resource | 20% | 中性默认 50,个股详情页可手动覆盖(MVP-1 不做自动资源估值) |
| Commodity | 10% | 对应商品 20/60 日动量(金/铜用期货,锂/铀/稀土用 ETF 代理) |
| Risk | 5% | 中性默认 50,可手动覆盖(越高越安全) |

每个分数的**逐项构成**(components)都随快照落库,个股详情页可见——这是系统的可解释性契约。

## 信号类型

| 类型 | 触发条件 |
|---|---|
| REL_VOL_SPIKE | 量 ≥ 3× 20 日均量 且 收涨 且 成交额 ≥ A$50k |
| BREAKOUT_60D / 252D | 收盘创 60/252 日新高 且 量 ≥ 1.5×(252 触发时抑制同日 60) |
| KEY_ANNOUNCEMENT | 当日新公告 base ≥ 70,或 price-sensitive 且 ≥ 60;**PLACEMENT/TRADING_HALT 无条件排除**(配售是稀释,停牌只是中性提示) |
| SCORE_CROSS_UP | Cycle Score 上穿 High Priority 线(75) |

低分触发同样记录(标 Ignore)——完整留痕,回测才能验证低分信号确实无参考价值。

## 回测口径(诚实优先)

- **入场价 = 信号后第一个交易日收盘价**。信号是收盘后算出的,用信号日收盘价当入场价是前视偏差(公告日尤甚)。
- **超额收益** = 信号收益 − 同期 OZR.AX(ASX 资源 ETF)收益,消解"商品牛市里啥信号都好"。
- 交易日按个股自身 K 线日历计(自动跳过停牌/假日);长期无 K 线的信号标 `unavailable`,不进统计但展示数量(生存者偏差透明化)。
- **replay 信号**:历史行情重放价格类规则所得,与 live 分开统计;不含标签/Cycle Score(历史公告不可得,不做假重构),故"按标签/分数段"统计仅含 live。
- n < 10 一律标"低样本"。

## 已知局限(设计上接受,不假装能解决)

1. **负面消息盲区**:ASX 小票公告标题永远往好里写,系统度量的是"正面故事强度",不是净情绪;坏消息表现为"没公告 + 阴跌",通过分数衰减间接体现,有滞后。
2. 同一事件常同日触发多个信号类型,总体汇总存在相关样本;以按类型分组的统计为主视角。
3. 锂/铀/稀土商品分用股票 ETF(LIT/URA/REMX)代理,有轻微循环引用;10% 权重下可控。
4. Resource/Risk 默认 50 是"死权重",区分度来自 F+A+C;默认下理论最高分 87.5。
5. ASX 公告接口只给最近 ~20 条,公告类信号无法回放,只能前向积累。
6. 公告源若被反爬(SourceBlockedError),pipeline 降级用库存公告并在日报标注,不会崩。
7. yfinance 对微盘股偶有缺数;`validate_seed.py` 用于剔除死票(本次 seed 时就抓出 MAU/XAM 已退市)。

## 测试

```bash
cd backend && .venv/bin/python -m pytest tests/ -q    # 111 个用例,全部离线(fixture),不联网

# Windows:
cd backend
.\.venv-win\Scripts\python.exe -m pytest tests -q
```

覆盖:公告分类优先级/词边界、指标精确值、评分阶梯边界、方向门槛与流动性地板、信号触发矩阵、幂等、回测入场价约定、基准超额、unavailable 判定、回放不污染标签统计。

## 项目结构

```
backend/app/
├── datasources/   # ASX 公告(markitdigital)、yfinance 日线、商品/基准
├── analysis/      # 纯函数:indicators / classifier / scoring / signals / ai_stub
├── services/      # pipeline 编排、回测、回放、日报、市场数据、配置
├── notify/        # Telegram(未配置优雅跳过)+ SMTP Email(未配置优雅跳过)
└── api/routes/    # stocks / signals / announcements / backtest / reports / config / admin
frontend/src/pages # Ranking / StockDetail / Signals / Backtest / Reports / Settings
scripts/           # seed_watchlist / validate_seed / run_pipeline / replay_signals
```

## Phase-2 方向

- `ClaudeAnalyzer` 实现 `AnnouncementAnalyzer`:MVP 已支持公告标题摘要/结构化提取;后续可扩展到公告 PDF 全文、grade/宽度/深度结构化提取、质量置信度
- 公告 HTML 抓取 fallback、按回测结果校准权重(数据驱动,不拍脑袋)
