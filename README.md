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
- **AI 分析层**: 默认 `noop` 不做额外调用;`rules_fulltext` 可抓公告文档/PDF 并用规则抽取 grade/宽度/深度/project/commodity;`claude` 在显式允许付费调用后用公告全文上下文做摘要/结构化提取

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
| `AI_ANALYZER` | `noop` / `rules_fulltext` / `claude`;默认不抓文档、不调用付费模型 |
| `AI_ANALYZER_ALLOW_PAID_CALLS` / `ANTHROPIC_API_KEY` | 只有 `AI_ANALYZER=claude` 且二者配置满足时才调用 Anthropic |

权重、标签阈值、信号阈值、商品映射、回测基准存在数据库 `app_config` 表,可在**设置页**改,无需重启。

## Cycle Score(固定权重,可在设置页调)

Cycle Score 衡量的是一只票"**资源故事正在形成多强的市场共识**",不是上涨概率、更不是买卖建议。分数由五块拼成,权重反映各自作为"共识证据"的分量,可在设置页调:

| 子分 | 权重 | 它回答的业务问题 |
|---|---|---|
| Funding | 35% | **有没有真金白银在往里进,且方向向上?** 权重最重,因为资金进场是"故事被认可"最直接的证据。看四件事:放量、突破新高、连续上涨、整周量能升温——但放量必须**收涨**(放量下跌是出货不是吸筹)且**成交额够真**(微盘股几笔单就能伪造暴量,设 A$50k 地板过滤)。突破取年/季/月最高的一档 |
| Announcement | 30% | **有没有强的消息催化,而且够新?** 把公告分成 11 类(钻探结果、资源升级、并购……)按含金量打底分,越新的越重(一个月前的好消息早被消化,归零),被交易所标"价格敏感"的加成。**30 天没公告 = 0**——沉默的票没有正在形成的故事,这正是雷达要区分的 |
| Resource | 20% | **矿本身值不值钱?** MVP 阶段机器无法可靠自动估资源量,与其给一个假装精确的错分,不如老实给中性 50,并留一个人工接口:分析师读了可研报告可手动覆盖 |
| Commodity | 10% | **对应的大宗商品在涨还是跌?** 给个股加一层顺风/逆风。金/铜用期货,锂/铀/稀土无可靠期货,用行业 ETF 代理 |
| Risk | 5% | **这只票安不安全?** 同样默认中性 50、人工可覆盖(越高越安全) |

因为 Resource/Risk 默认都卡在 50,一只票的排名实际由 **资金 + 公告 + 商品** 三块拉开;默认状态下满分只到 87.5,不是 100。

**可解释性是这套系统的核心承诺**:每个分数都能点开,看到它是怎么来的——比如放量那块会显示 `20/40 · rel_vol 2.48x · 当日 +4.35% · 成交额 A$2206k`,公告那块会显示 `82 ← 钻探结果 base 85 × 时效 0.8 × 价格敏感 1.2`。哪怕给了 0 分,也会说明**为什么是 0**(是放量下跌?还是成交额不够?)。评分刻意用"阶梯给分"而非拟合公式,就是为了让每一分都能说清楚、能被质疑——它是给人做研究用的工具,不是一个让你盲信的黑箱。

## 信号类型

Cycle Score 是每天的连续状态,信号则是"**值得单独记一笔的时刻**"——今天这只票发生了一件事,把它留痕下来,日后用回测检验它到底有没有参考价值。四类信号各捕捉一种"有事发生":

| 类型 | 捕捉什么 | 触发条件 |
|---|---|---|
| REL_VOL_SPIKE | 资金异动 | 成交量 ≥ 3 倍 20 日均量,且当天收涨,且成交额 ≥ A$50k |
| BREAKOUT_60D / 252D | 价格突破历史天花板 | 收盘创 60/252 日新高,**且带量**(≥1.5 倍);创年新高时不重复记季新高 |
| KEY_ANNOUNCEMENT | 重大消息催化 | 当天新公告足够强;**配售、停牌无条件排除**——它们标题看着像大事,实则一个是稀释股东、一个只是中性提示,不该当利好 |
| SCORE_CROSS_UP | 综合故事刚"升级" | Cycle Score 从下方**上穿** High Priority 线(75)的那一刻,只在跨过去时记一次,不会天天重复 |

信号的门槛比评分更严,因为信号要拿去回测,必须干净。两个体现这点的地方:**突破必须带量**——无量的新高往往第二天就回落,是假突破;**放量必须收涨**——放量下跌是有人在出货,量越大越糟。

**每条信号都附一句人话和一组原始数字**,比如 `成交量是 20 日均量的 3.3 倍,当天 +3.0%`,以及背后的收盘价、放量倍数、成交额等,信号页和个股详情页都能看到,方便你自己复核。

**低分触发也照样记录**(标 Ignore)。这不是冗余——只有把低分信号也留痕,回测才能验证"低分信号确实没参考价值"这个命题。这是系统"用数据检验自己"的根基。

## 回测口径(诚实优先)

回测要回答的问题是:**这些信号在历史上,到底有没有参考价值?** 为了不自欺,每条口径都优先诚实:

- **入场价 = 信号后第一个交易日收盘价,不是信号当天**。信号是收盘后才算出来的,用当天收盘价当买入价等于偷看未来(公告日尤其严重)。用次日收盘价,量的才是"这份晚间报告第二天还值不值得行动"——唯一诚实的读法。
- **看超额收益,不看绝对收益**:信号收益减去同期资源 ETF(OZR.AX)收益。要证明的是信号**跑赢了板块**,而不是"商品牛市里随便什么信号都涨"。
- **生存者偏差透明化**:退市或长期停牌、拿不到后续行情的信号,标为"无法回填",不进统计但**照样计数展示**——不假装这些失败的票不存在。
- **历史重放不造假**:价量类信号可以用历史行情重放(replay),但历史公告拿不到,所以重放信号不带标签和 Cycle Score。系统拒绝"用今天的规则假装重构历史公告"。因此"按标签/按分数段"的统计只用真实积累的 live 信号,不被重放数据污染。
- **样本不足如实标注**:每组样本数 < 10 一律标"低样本",提醒你别当真。

**每个统计数字都能下钻**:任意一格胜率/均值/超额,都可追到构成它的每一条信号、每个持有期的入场价与收益,逐笔核对。回测页给你的是可审计的证据,不是一个漂亮但无法验证的结论。

## 已知局限(设计上接受,不假装能解决)

诚实优先的一部分,就是把系统做不到的事明确说出来,而不是假装能解决:

1. **负面消息盲区**:ASX 小票公告标题永远往好里写,系统度量的是"正面故事强度",不是净情绪。坏消息不会有公告,只表现为"没公告 + 阴跌",靠分数衰减间接、滞后地反映。这是最根本的边界——外部具名分析可以部分补盲,但刻意不并入 Cycle Score。
2. **相关样本**:同一件事常同一天触发好几类信号(放量和突破一起来),汇总时这些样本不独立。所以以"按信号类型分组"为主视角,并对总数去重。
3. **商品代理的循环引用**:锂/铀/稀土没有可靠期货,用行业 ETF 代理,等于用矿业股给矿业股打分,有轻微循环;10% 权重下影响可控。
4. **Resource/Risk 是"死权重"**:两者默认都是 50,对排名不产生区分度,真正拉开差距的是资金/公告/商品三块;默认状态下满分只到 87.5。人工覆盖是把分析师的定性判断显式注入评分的接口。
5. **公告只能前向积累**:ASX 公告接口只返回最近约 20 条,更早的历史公告拿不到,所以公告类信号无法回放,只能从今天起向前攒——这也意味着任何依赖公告的模型几乎没有历史训练数据。
6. **数据源被封不会崩**:公告源若被反爬,系统降级使用库存公告,并在日报里标注,而不是直接挂掉。
7. **微盘股偶有缺数**:行情源对微盘股偶尔缺数据;配套的校验脚本用于剔除已退市的死票(本次建池时就抓出 MAU/XAM 已退市)。

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

- `ClaudeAnalyzer` 已支持公告文档/PDF 全文上下文;`rules_fulltext` 已支持常见钻探拦截 grade/宽度/深度/project/commodity 抽取
- 更强的公告 HTML fallback、资源量表格抽取、按回测结果校准权重(数据驱动,不拍脑袋)
