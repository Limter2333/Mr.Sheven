# 06 - 项目实施方案（MVP → 上线）

> 输入基线：新版《酒类评测App完整业务流程需求文档》+ 本项目 01~05 号文档。
> 已确认决策：后端**全 Python**；客户端**原生 App**；MVP 识别 = **OCR 中文背标主路径 + 条码快速通道**（裁决 C12，2026-10-04 取代原"MVP 仅扫码，不做 OCR"）；不做 ASR 强攻。
> 本文档是工程实施总纲；各模块详设（Prompt 全文、DDL 定稿、接口文档）随开发在对应阶段产出。

---

## 一、需求冲突与统一裁决

共 12 处不一致，裁决如下（C9 已被 C12 推翻，保留存档）：

| # | 冲突点 | 裁决 | 理由 |
|---|---|---|---|
| C1 | 新文档提 L1 缓存用 Caffeine（Java 专属库）vs 02 文档已选 Python | L1 用 `cachetools.TTLCache`（进程内 TTL 缓存），语义等价 | 已确认全 Python；探针资产（yt-dlp/dashscope）直接复用 |
| C2 | 新文档通篇说「App」vs 决策 D7 说小程序/H5 | **原生 App（Flutter 跨平台）**；备案工作流非阻塞，先出 DEMO 再考虑合规（裁决 C11） | 原生 App 体验更好、扫码能力更强、Flutter 一套代码双端 |
| C3 | 无评测时：二(五)说给温情提示文案 vs 四(六)说隐藏模块绝不提示 | **隐藏空评测模块 + 展示温情提示卡**（"暂无博主评测…建议谨慎购买" + 同酒庄/同品类兜底 + 口感反馈入口） | 核心定位是"避坑指南"，明确风险提示就是产品卖点 |
| C4 | 去重索引 `UNIQUE(mid, pubdate)` | 改为 `UNIQUE(mid, pubdate_date, title_hash)`（UP主 + 自然日 + 清洗标题哈希） | B站 pubdate 是秒级时间戳，加 title_hash 才精确命中删旧重传/多版本重发场景 |
| C5 | 重复评测且评分变化：UPDATE 覆盖 vs 保留新增 | **保留旧记录 + 新增记录**（`prev_review_id` 演变链 + `score_trend`/`trend_reason`） | 承接 D4"分博主展示"；软丢弃可回溯、可人工撤销 |
| C6 | 02 文档说生产库 PostgreSQL vs 新文档说 MySQL | **MySQL 8.0.x 最新补丁版**（≥8.0.40，Docker 用 `mysql:8.0` 跟随最新补丁） | JSON 字段、唯一索引、生成列均满足需求 |
| C7 | 探针选品仅红酒 vs D2 说"红酒放二期" | **三品类全做**（红酒、威士忌、金酒） | 红酒不再需要"放二期"；三品类覆盖更全面；正标花体识别难由中文背标 OCR 补偿（裁决 C12） |
| C8 | ASR "绝不强攻" vs "三级备胎" | **绝不强攻**：字幕失败直接跳过，标记 NO_SUBTITLE，不做 ASR | 等平台 AI 字幕覆盖率提升后再考虑；成本控制优先 |
| C9 | 识别端探针实验缺失 / OCR 技术风险 | ~~**MVP 不做 OCR**，全部依赖条形码识别~~ **已被 C12 推翻**（2026-10-04） | 原裁决假设"条形码技术成熟可靠"，被 C10 覆盖率实测证伪（进口酒覆盖≈0）；OCR 背标真瓶验证反而通过 |
| C10 | 第三方条码 API 覆盖率验证时机 | **P0 阶段做 100 个进口酒条码覆盖率抽样测试**；**2026-10-04 已执行，结论：进口酒不达标** | 阿里云条码 API 仅支持 69 前缀 13 位/069 前缀 14 位国内商品；Open Food Facts/go-upc 对真实进口酒条码（格鲁吉亚 486、南非 600 前缀）均无收录 → 触发 C12 转向，印证"提前测"的价值 |
| C11 | 备案时间线几乎无余量 | **先本地开发 DEMO，不急于上架市场**；备案和软著后续再考虑 | MVP 目标是把产品做出来验证，不是正式上架；开发期间用内测分发验证 |
| C12 | 条码覆盖率实测失败后的识别路径（2026-10-04 新增） | **OCR 中文背标主路径 + 条码快速通道**：拍背标 → OCR → LLM 结构化提取 → 三档语义匹配（EXACT 同款 / SERIES 同系列另一款 / NONE 无关）库内 SPU；识别成功且可读到条码时回写 barcode↔SPU 绑定（自增长） | 进口酒中文背标为法规强制印刷、标准字体、字段全（品名/原产国/产区/品种/酒精度/净含量/进口商），OCR 友好；真瓶端到端验证通过（LLM 正确拒绝跨款绑定，防幻觉）；条码保留为已绑定项的零成本快速通道 |

> ✅ C1~C11 裁决已于 2026-10-02 全部经用户确认；C12 于 2026-10-04 依据 C10 覆盖率实测（不达标）+ OCR 真瓶验证（通过）新增，已经用户确认。

---

## 二、总体架构

```
┌─────────────────────────────── 离线：数据管道（夜间跑批） ───────────────────────────────┐
│                                                                                          │
│  [爬虫模块]──▶[字幕模块]──▶[清洗模块]──▶[查重规则引擎]──┬─(无疑似)──▶[LLM结构化提取]      │
│   B站列表      BiliCC字幕     去时间轴        bvid唯一索引 │                                 │
│   state校验    yt-dlp兜底     去口播广告      标题清洗比对 │                                 │
│   写任务表     失败→标记      输出纯文本      (mid,日,哈希)└─(同UP+同酒)─▶[LLM对比研判]     │
│   WAITING_SUBTITLE                                            is_duplicate/trend/reason   │
│        ▲                                                            │                     │
│        └────[补录Patch Job 凌晨重扫]                                ▼                     │
│                                              [SPU归一化]──▶[MySQL 入库]                   │
│                                               别名表匹配      spu / review / video_review │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                     │ 读
                                     ▼
┌─────────────────────────────── 在线：查询服务（FastAPI） ──────────────────────────────┐
│  [限流中间件]──▶[L1 TTLCache]──▶[L2 Redis]──┬─(条码已绑定SPU)─────────▶[组装响应]      │
│   10次/分/IP      进程内5min      命中即返回  │  快速通道（裁决C12）                      │
│                                              ├─(条码未绑定)─▶[第三方条码API]──▶[前置过滤]│
│                                              │   69前缀→阿里云 / 其他→OFF（辅助通道）    │
│                                              └─(拍酒标图片)─▶[OCR背标]─▶[LLM提取+三档匹配]│
│                                                   OCR 主路径（裁决C12） EXACT/SERIES/NONE│
│                                                        │匹配成功                        │
│                                                        ▼                                │
│              [回写条码↔SPU绑定(自增长)]──▶[落库MySQL+回写缓存]──▶[关联review]──▶[组装响应]│
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                     │ HTTPS
                                     ▼
┌─────────────────────────────── 客户端：原生 App（Flutter） ────────────────────────────┐
│   扫码页（条码快速通道 + 拍背标入口）──▶ 结果页（有评测 / 无评测提示卡 / 非酒 / 查无 四形态；SERIES 命中加"同系列另一款"标注）│
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**异步架构裁决**：新文档给了 RabbitMQ / Redis List / 数据库任务表三选项，MVP 选**数据库任务表**（`video_review.status` 状态机 + `llm_task` 表）+ APScheduler 定时消费。理由：单机单进程够用、状态与业务数据同库天然事务一致、零新增组件；量级起来后平滑换 Redis List/RQ，消费逻辑不变。

---

## 三、技术栈清单

| 层 | 选型 | 说明 |
|---|---|---|
| 语言/依赖 | Python 3.12 + uv | 沿用 02 文档映射，探针资产直接复用 |
| 在线服务 | FastAPI + uvicorn + Pydantic v2 | 扫码查询 API、限流中间件 |
| ORM/迁移 | SQLAlchemy 2.0 + Alembic | MySQL 8.0.x 最新补丁版（裁决 C6） |
| L1 缓存 | `cachetools.TTLCache(maxsize=10_000, ttl=300)` | Caffeine 的 Python 等价方案（裁决 C1）：进程内、带 TTL 与容量淘汰；实现细节见第六节 |
| L2 缓存 | Redis 7 + `redis-py`（`redis.asyncio`），Docker 同机部署 | 命中响应 / 空值标记 / 非酒标记 / 限流计数 |
| 离线管道 | 同仓库独立 package，入口 `python -m pipeline.scheduler` | 与在线服务分离部署（≈ batch job 与 web app 分模块） |
| 调度 | APScheduler | 爬取每 20 分钟（每次 2 页断点续爬）/ 夜间跑批 22:00 / 补录 03:00 |
| 视频/字幕 | bilibili-api-python（列表+state）+ yt-dlp（字幕/音频）+ BiliBiliCCSubtitle（备选） | cookies.txt 纪律沿用 05 文档 |
| LLM（统一百炼） | 提取/对比/**酒标匹配研判**：qwen-plus（疑难升级 qwen-max）；OCR：阿里云读光（备选 qwen-vl-ocr） | 单一厂商便于成本核算；夜间 22:00 后跑批吃减免时段；**OCR+酒标匹配已进 MVP**（裁决 C12）；ASR（qwen3-asr-flash-filetrans）仍留 V2（裁决 C8） |
| 模糊匹配 | rapidfuzz（标题相似度 / SPU 名称归一） | 不引入向量检索（新文档原则二） |
| 客户端 | Flutter（`mobile_scanner`=ML Kit 扫码 + `image_picker`/`camera` 拍背标） | 一套代码 iOS+Android；MVP = 条码快速通道 + 拍背标 OCR 主路径（裁决 C12）；备选 uni-app（可兼出小程序当流量侧门） |
| 部署 | 单机 Docker Compose：mysql + redis + api + scheduler + nginx | 2C4G 云服务器起步 |
| OCR 数据源 | 阿里云读光 OCR（文字识别，主）+ 百炼 qwen-vl-ocr（备选） | 裁决 C12 新增；识别中文背标（标准印刷字体），提取品名/原产国/产区/品种/酒精度/净含量/进口商 |
| 条码数据源 | 阿里云API市场条码查询（仅 69 前缀 13 位/069 前缀 14 位国内商品）+ Open Food Facts（免费兜底） | **覆盖率测试已于 2026-10-04 执行：进口酒不达标**（裁决 C10 结论）→ 条码降级为快速通道/国内商品辅助，识别主路径改为 OCR 背标（裁决 C12） |

---

## 四、数据库设计（MVP，MySQL 8.0.x 最新补丁版）

```sql
-- 酒款主表（SPU）。年份/酒龄字段预留但 MVP 不启用（裁决：扁平化只认酒名）
CREATE TABLE spu (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(200) NOT NULL,           -- 归一化名称
  name_raw      VARCHAR(200),                    -- 首次入库原始名
  brand         VARCHAR(100), category VARCHAR(20),   -- wine/whisky/gin/...
  country       VARCHAR(50),  region VARCHAR(100),
  abv           DECIMAL(4,1), volume_ml INT,
  vintage_year  SMALLINT NULL,                   -- V2 预留（葡萄酒年份）
  age_years     SMALLINT NULL,                   -- V2 预留（威士忌酒龄）
  possible_dup_of BIGINT NULL,                   -- 归一化中置信度命中的待人工合并对象
  source        VARCHAR(20),                     -- llm_extract/barcode_api/manual
  created_at    DATETIME, updated_at DATETIME,
  UNIQUE KEY uk_name (name)
);

-- 别名表（承接 D6 实体对齐；种子 = 博主视频标题清洗 + LLM 抽取）
CREATE TABLE spu_alias (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  spu_id BIGINT NOT NULL,
  alias VARCHAR(200) NOT NULL,
  alias_norm VARCHAR(200) NOT NULL,              -- 小写去符号归一
  source VARCHAR(20),                            -- llm/manual/barcode_api
  UNIQUE KEY uk_alias (alias_norm), KEY idx_spu (spu_id)
);

-- 条码映射（一酒多码；含非酒拦截与第三方原始报文）
CREATE TABLE barcode (
  code          VARCHAR(32) PRIMARY KEY,         -- EAN-13/UPC
  spu_id        BIGINT NULL,                     -- NULL = 已知码但未关联酒款
  is_non_wine   TINYINT DEFAULT 0,
  category_hint VARCHAR(50),                     -- 第三方分类原文
  raw_json      JSON,
  source        VARCHAR(20), created_at DATETIME,
  KEY idx_spu (spu_id)
);

-- 视频评测表（管道状态机载体）
CREATE TABLE video_review (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  bvid VARCHAR(12) NOT NULL,
  mid BIGINT NOT NULL, uploader_name VARCHAR(100),
  title VARCHAR(500),
  title_clean VARCHAR(500),                      -- 去【】修饰词/年份/符号，统一小写
  title_hash CHAR(32),                           -- MD5(title_clean)
  pubdate DATETIME,
  pubdate_date DATE AS (DATE(pubdate)) STORED,   -- 生成列，供去重索引
  duration_sec INT,
  status VARCHAR(24) NOT NULL DEFAULT 'NEW',
  subtitle_text MEDIUMTEXT,                      -- 清洗后纯文本
  fail_reason VARCHAR(500), retry_count INT DEFAULT 0,
  created_at DATETIME, updated_at DATETIME,
  UNIQUE KEY uk_bvid (bvid),                                   -- 去重第一层
  UNIQUE KEY uk_mid_day_title (mid, pubdate_date, title_hash), -- 去重第三层（裁决 C4）
  KEY idx_status (status), KEY idx_title_hash (title_hash)
);
-- status 取值：NEW / NO_SUBTITLE / CLEANED / DUP_SUSPECT /
--              EXTRACTING / EXTRACTED / DUPLICATE_CONFIRMED / DISCARDED / FAILED

-- 评测记录表（一视频多酒、一酒多博主、同博主重评走演变链）
CREATE TABLE review (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  spu_id BIGINT NOT NULL, video_review_id BIGINT NOT NULL,
  mid BIGINT NOT NULL,                           -- 冗余，查"某博主最新评"免 join
  score_raw VARCHAR(20), score_type VARCHAR(20), -- pct100/scale10/none（承接 D5 原始层）
  verdict VARCHAR(10),                           -- recommend/neutral/avoid（归一层三档）
  flavor_tags JSON, recommend_index TINYINT,
  quote TEXT,                                    -- 逐字原话摘录（防幻觉锚点）
  ts_start INT, ts_end INT,                      -- 视频内起止秒，支持"跳到 12:34"
  score_trend VARCHAR(4), trend_reason VARCHAR(500),  -- UP/DOWN/SAME + 博主自述原因
  prev_review_id BIGINT NULL,                    -- 演变链（裁决 C5）
  confidence DECIMAL(3,2),
  is_latest TINYINT DEFAULT 1,
  created_at DATETIME,
  KEY idx_spu (spu_id), KEY idx_video (video_review_id),
  KEY idx_spu_mid_latest (spu_id, mid, is_latest)
);

-- LLM 任务表（COMPARE 对比 / EXTRACT 提取，统一排队重试）
CREATE TABLE llm_task (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_type VARCHAR(20), video_review_id BIGINT,
  payload JSON,                                  -- 输入：新旧摘要 or 清洗后全文
  status VARCHAR(20) DEFAULT 'PENDING',          -- PENDING/RUNNING/DONE/FAILED
  result_json JSON, error_msg VARCHAR(500),
  retry_count INT DEFAULT 0,
  created_at DATETIME, updated_at DATETIME,
  KEY idx_status_type (status, task_type)
);

-- 扫码日志（业务指标 + 缺漏反哺抓取优先级，呼应 01 文档命中率缓解）
CREATE TABLE scan_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  barcode VARCHAR(32),
  result_type VARCHAR(20),                       -- HIT_REVIEW/HIT_NO_REVIEW/NOT_WINE/NOT_FOUND
  ip_hash CHAR(64), created_at DATETIME,         -- 不存原始 IP
  KEY idx_barcode (barcode), KEY idx_created (created_at)
);
```

**Redis Key 设计**（对应新文档三道防线）：

| Key | 内容 | TTL | 用途 |
|---|---|---|---|
| `wine:bc:{code}` | 组装后的完整响应 JSON | 7 天 | L2 正常命中 |
| `wine:bc:{code}` | `{"status":"NOT_FOUND"}` | 5 分钟 | 空值标记防穿透（第三方查无此码） |
| `wine:bc:{code}` | `{"status":"NOT_WINE"}` | 7 天 | 非酒拦截缓存（二扫不再调第三方） |
| `rl:{ip}:{yyyymmddHHMM}` | INCR 计数 | 2 分钟 | 限流：>10 次/分 → 429 |

> 空值/非酒标记与正常命中共用同一 key 空间，靠 status 字段区分——等价于新文档的独立 `non_wine:` key，实现更简。

---

## 五、服务端数据管道实施（对应新文档三·六步）

### 状态机

```
NEW ──字幕下载成功──▶ CLEANED ──查重通过(无疑似)──────────────▶ EXTRACTING ──▶ EXTRACTED ──▶ (入库 review)
 │                      │                                        ▲
 │                      └─同UP主+同酒疑似─▶ DUP_SUSPECT          │
 │                                          └─ llm_task(COMPARE)─┤
 │                                             ├ 非重复 ─────────┘
 │                                             ├ 重复+评分变化 ──▶ EXTRACTING（新 review 挂演变链）
 │                                             └ 重复+无变化 ────▶ DISCARDED（仅更新 last_reviewed）
 └─字幕失败─▶ NO_SUBTITLE（终态，日志留痕，裁决 C8：不做 ASR，直接跳过）
 任一环节异常─▶ FAILED（retry_count<3 夜间重排队；≥3 终态待人工）
```

### 模块实施要点

| 步骤 | 模块 | 实施要点 |
|---|---|---|
| 1 爬取 | `pipeline/crawler` | httpx + 完整浏览器请求头（Cookie/UA/Referer/Sec-Fetch）直调 `x/space/arc/search`；**先校验 state 字段**剔除已删/私密/动态专栏；`INSERT IGNORE` 靠 uk_bvid 天然过滤已入库（捕获 Duplicate 即跳过）；白天只写元数据，不做重活。⚠️ **B 站限频极严**（见下方"爬虫限频策略"） |
| 2 字幕 | `pipeline/subtitle` | 主通道 BiliBiliCCSubtitle（携带 TOKEN）；yt-dlp `--write-subs --sub-langs ai-zh` 备选；失败**直接跳过，不做 ASR**（裁决 C8），标记 NO_SUBTITLE 记日志 `[跳过] BVID: BV1xxx 暂无字幕` 继续下一个，不阻塞主流程；不再有 WAITING_SUBTITLE 状态和补录重试 |
| 2b 清洗 | `pipeline/cleaner` | 正则去时间轴/乱码；规则去开场白、求三连、广告口播（维护可配置的黑名单短语表）；产出干净纯文本存 `subtitle_text` |
| 3 查重 | `pipeline/dedup` | 三层防线：① uk_bvid（硬）② 清洗标题比对：同 mid 分组内 title_hash 相等或 rapidfuzz token_set_ratio≥90 → DUP_SUSPECT ③ uk_mid_day_title（硬，拦截即日志留痕可人工找回）。**跨 UP 主搬运防线**：title_hash 相同但 mid 不同 → 不硬拦（保护 D1 多博主评同酒的合法数据），比对双方字幕文本相似度 ≥95% 才判搬运丢弃 |
| 4 对比研判 | `pipeline/llm/compare` | 仅"同UP主+同款酒"才喂 LLM；Prompt 输出 `{is_duplicate, old_score, new_score, score_trend, reason_for_change}`；**LLM 定位=数据提取器非裁判**（不让它重新打分/评判谁更客观）；JSON 解析必须 try-catch，失败→FAILED 重试≤3 |
| 5 结构化提取 | `pipeline/llm/extract` | 复用 03 文档探针验证过的 Schema（product_name_raw/score_raw+score_type/verdict/quote/flavor_tags/recommend_index/timestamps/confidence）+ 三条防幻觉纪律（只抽实际评测的、拿不准填 null、quote 逐字）；一视频多酒输出数组逐条入库 |
| 6 归一化入库 | `pipeline/normalize` | 名称归一（小写去符号）→ ① `spu.name` 精确 ② `spu_alias.alias_norm` 精确 ③ rapidfuzz：≥90 自动绑定（写日志+新别名入 alias 表）；75~89 建新 SPU 并填 `possible_dup_of` 待人工合并；<75 建新 SPU。写入策略按裁决 C5：新评测 INSERT；重复有变化→新增 review 挂 `prev_review_id`+trend；重复无变化→DISCARDED |

### 调度（APScheduler）

| 频率 | 任务 | 说明 |
|---|---|---|
| 每 20 分钟 | 爬取 Job | 每次拉取 2 页（40 条），**断点续爬**（根据已入库数量自动算起始页）；避免触发 B 站限频 |
| 22:00 | 夜间跑批 Job | 消费 status=NEW/CLEANED/DUP_SUSPECT/FAILED(retry<3)；字幕→清洗→查重→LLM；吃百炼夜间减免时段、避高峰限流 |
| 03:00 | 补录 Patch Job | 重扫 NO_SUBTITLE 视频再试字幕（B站 AI 字幕异步生成，隔天才挂载是常态）；成功→推入正常流水线；仍无字幕则保持 NO_SUBTITLE |
| 08:00 | 日报 Job | 聚合前一日管道/扫码/缺漏指标 |

### 爬虫限频策略（⚠️ 重新实现必读）

> B 站空间 API（`x/space/arc/search`）是浏览器内部接口，限频极严。**即使带 Cookie + 模拟浏览器头，每个 IP 每 1~2 分钟只能安全调用 1~2 次**。违反会触发 `-799`（临时限频）或 `412`（风控封禁 IP，可持续数分钟到数小时）。

**踩坑记录与经验教训：**

| # | 错误做法 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | 连续翻页，间隔 3~10 秒 | 2~3 页即触发 -799 限频 | 间隔 30~60 秒随机延迟 |
| 2 | 固定间隔请求 | 节奏规律，被识别为脚本 | 随机延迟（`random.uniform`） |
| 3 | 被限频后立刻重试 | 加深封禁 | 直接停止，等下次调度 |
| 4 | 一次爬完所有页 | 请求密度过高 | 每次最多 2 页，断点续爬 |
| 5 | 单一 User-Agent | 容易被标记 | 5 种 UA 随机轮换 |
| 6 | 不带完整浏览器头 | 直接 412 | Cookie + Referer + Sec-Fetch + Origin 全套 |
| 7 | 用 `bilibili-api-python` | 该库自带的请求头不够真实，照样 412 | httpx 直调，自建请求头 |

**正确参数组合（已验证可用）：**

```
每次请求间隔：30~60 秒随机
每页条数：20
每次运行页数：≤2 页（断点续爬）
UA 轮换：5 种浏览器 UA
首请求前延迟：2~5 秒随机
重试策略：遇到 -799/412 直接停止，等下一轮调度（20 分钟后）
```

**断点续爬机制：** 每次运行时查询 `video_review` 表中该 mid 的已入库数量，计算 `start_page = count // 20 + 1`，从上次中断处继续。多次调度自动完成全量爬取。

---

## 六、客户端查询服务实施（对应新文档四·六步）

### 接口契约

```
GET  /api/v1/scan?barcode={code}      # 条码链路（快速通道：已绑定 SPU 直接返回；辅助：第三方 API）
POST /api/v1/scan-label               # OCR 主链路（裁决 C12）：酒标图片 → OCR → LLM 提取 → 三档匹配
GET  /api/v1/spu/{id}/reviews         # 详情页（含演变链）
GET  /healthz                         # 探活
```

> `/api/v1/scan-label`（裁决 C12）：multipart 上传图片，可附带客户端同帧读到的条码（识别成功后回写 barcode↔SPU 绑定，自增长）；响应复用 scan 统一信封，额外带 `match_level`（EXACT/SERIES/NONE）与 OCR 提取字段（品名/原产国/产区/品种/酒精度/净含量/进口商）。

**scan 响应**（统一信封，客户端按 status 渲染四形态）：

```json
{
  "status": "HIT_REVIEW | HIT_NO_REVIEW | NOT_WINE | NOT_FOUND",
  "wine": {
    "name": "拉菲古堡干红", "brand": "拉菲", "category": "wine",
    "country": "法国", "region": "波亚克", "abv": 12.5,
    "volume_ml": 750, "barcode": "3274080005003"
  },
  "reviews": [{
    "blogger": {"name": "品酒大师老王", "mid": 123456, "platform": "bilibili"},
    "score_raw": "92", "score_type": "pct100", "verdict": "recommend",
    "flavor_tags": ["黑醋栗", "雪松", "烟草"], "recommend_index": 5,
    "quote": "……", "score_trend": "UP", "trend_reason": "这次醒足两小时……",
    "video": {"bvid": "BV1xxx", "title": "……", "url": "https://www.bilibili.com/video/BV1xxx", "ts_start": 754},
    "reviewed_at": "2026-05-01"
  }],
  "fallback": [{"spu_id": 1, "name": "拉菲珍宝干红"}]   // 无评测时同酒庄/同品类兜底，可空
}
```

### 请求处理流

**条码链路（GET /scan，六步）**：

1. **限流中间件**：`rl:{ip}:{minute}` INCR >10 → 429（网关级，最先执行）
2. **L1** TTLCache → **L2** Redis：命中直接返回（含 NOT_FOUND/NOT_WINE 标记命中）
3. **barcode 表**：已绑定 SPU → 直接进第 5 步（快速通道，裁决 C12）；未绑定 → 第三方条码 API（69 前缀 13 位/069 前缀 14 位 → 阿里云；其他 → Open Food Facts）：
   - 分类不含"酒/饮料/食品"→ 写 `NOT_WINE` 标记（TTL 7天）→ 返回 `NOT_WINE`（客户端码 20001）
   - 查无此码 → 写 `NOT_FOUND` 标记（TTL 5min 防穿透）→ 返回 NOT_FOUND，**并引导用户改拍中文背标走 OCR 主链路**（裁决 C12，不再直接终态）
4. **落库+回写**：酒品信息写 MySQL（barcode 表 + 归一化建/绑 SPU）→ 回写 Redis + L1
5. **评测关联**：`barcode.spu_id → review(is_latest=1)`，MVP 只认酒名不认年份（命中即返回）
6. **组装**：有评测 → `HIT_REVIEW` 全量；无评测 → `HIT_NO_REVIEW`（reviews=[]，带 fallback 兜底），每次扫码写 scan_log

**OCR 主链路（POST /scan-label，裁决 C12）**：

1. **限流**：同上；OCR+LLM 有真实成本，阈值单独收紧（如 5 次/分/IP）
2. **OCR**：图片 → 阿里云读光 OCR（备选 qwen-vl-ocr；调试期支持直接传文本透传）→ 背标全文
3. **LLM 结构化提取**：品名/原产国/产区/品种/酒精度/净含量/进口商/年份——缺失字段置 null，不猜
4. **三档语义匹配**（LLM 对库内候选 SPU 研判；防幻觉纪律：宁可不绑也不乱绑）：
   - `EXACT` 同款 → 正常评测流程（同条码链路第 5~6 步）
   - `SERIES` 同系列不同款（如拍"橡木桶五号"命中被评测的"珍藏"）→ 返回该系列评测 + `match_level=SERIES`，客户端显著标注"博主评测的是同系列另一款"
   - `NONE` 无关/库内没有 → `NOT_FOUND` + 催更入口
5. **自增长回写**：识别成功且附带条码 → 写 barcode↔SPU 绑定，同瓶下次扫码走快速通道（零成本、零延迟）
6. **组装**：复用 scan 统一信封 + `match_level` + OCR 提取字段；写 scan_log（result_type 增加 SERIES 维度，反哺抓取优先级）

### 多级缓存实现（Python，裁决 C1 落地）

Caffeine + Redis 两级组合的 Python 等价方案 = **`cachetools.TTLCache`（L1 进程内）+ `redis.asyncio`（L2 分布式）**：

```python
from cachetools import TTLCache
import redis.asyncio as aioredis

_l1 = TTLCache(maxsize=10_000, ttl=300)      # 进程内，5min，超容自动淘汰（≈ 单机 Caffeine）
_r  = aioredis.Redis(decode_responses=True)

async def cache_get(barcode: str) -> dict | None:
    if (hit := _l1.get(barcode)) is not None:            # L1：微秒级
        return hit
    if raw := await _r.get(f"wine:bc:{barcode}"):        # L2：毫秒级
        hit = json.loads(raw)
        _l1[barcode] = hit                               # 回填 L1
        return hit
    return None                                          # 两级未命中 → 第三方条码 API

async def cache_put(barcode: str, resp: dict, ttl: int) -> None:
    _l1[barcode] = resp
    await _r.set(f"wine:bc:{barcode}",
                 json.dumps(resp, ensure_ascii=False), ex=ttl)
```

三条执行约定：
1. **多 worker 语义**：每个 uvicorn worker 进程各持一份 L1（等同 Caffeine 多节点部署情形）；L1 TTL 仅 5 分钟且数据更新集中在夜间跑批，进程间不一致窗口可忽略
2. **失效策略**：MVP 全靠 TTL 自然过期，不做主动失效；夜间跑批变更某酒评测时顺手 `DEL wine:bc:{code}`，L1 最多 5 分钟后自动过期
3. **线程安全**：FastAPI async handler 全部跑在事件循环单线程，TTLCache 无需加锁；若未来放进线程池执行，改用 `cachetools.cached` 装饰器并传 `lock` 参数

### 渲染规则（裁决 C3 落地）

- `HIT_REVIEW`：突出权威背书——"92分 | 品酒大师老王（B站知名酒类博主）"+ 风味标签 + 原话摘录 + 跳视频（带 ts_start 定位）
- **SERIES 命中**（`match_level=SERIES`，裁决 C12）：照常展示评测卡，但顶部显著标注"⚠️ 博主评测的是同系列另一款（如你拍的是'橡木桶五号'，评测对象为'珍藏'），结论仅供参考" + "我尝过/催更"入口
- `HIT_NO_REVIEW`：隐藏空评测模块，展示提示卡："这款酒目前还没有被博主评测过哦。在酒圈里，没有口碑的酒往往意味着风险较高，建议您谨慎购买。" + 兜底推荐 + "我尝过/催更"反馈入口（数据进 scan_log，反哺抓取优先级）
- `NOT_WINE`："扫描到的不是酒类商品哦，请对准酒瓶上的条形码。"
- `NOT_FOUND`："抱歉，未找到该商品信息。这可能是未收录的冷门酒或商品码已失效。" + "催更"反馈入口（数据进 scan_log，反哺抓取优先级）；条码查无时追加引导"可拍摄酒瓶中文背标识别"（裁决 C12）

---

## 七、原生 App 实施（Flutter）

### 页面清单（MVP 共 4 页）

| 页面 | 要点 |
|---|---|
| 扫码主页 | `mobile_scanner`（ML Kit）识别 EAN-13/UPC；客户端先校验条码格式合法性（分支A：格式非法本地直接提示，不打后端）；**"拍酒标"入口**（裁决 C12）：引导对准中文背标（避反光、占满取景框）拍摄上传 `/scan-label`，可同帧附带读到的条码 |
| 结果页 | 四形态渲染（见上节）；评测卡分博主展示（D4），演变链折叠展示"上次 8.0 → 本次 8.5，原因……" |
| 反馈页 | 口感反馈/催更表单（V1 只落库不展示，UGC 是 V2） |
| 设置/关于 | 隐私政策、权限说明——**正式上架时为硬性要求**；DEMO 阶段可精简 |

> 拍酒标识别已纳入 MVP（裁决 C12，取代 C9）：拍摄入口位于扫码主页与"查无此码"结果页；V2 可加取景框实时 OCR 预检。

### 合规备案工作流（裁决 C11：先出 DEMO，备案后续再启动）

> 当前目标：本地开发出 DEMO 验证产品，不要求正式上架市场。备案和软著在产品验证通过后再考虑。

| 事项 | 周期 | 依赖 | 说明 |
|---|---|---|---|
| 域名购买 + ICP 备案 | 2~4 周 | 云服务器 | **产品验证通过后启动** |
| 软件著作权申请 | 普通 1~2 月 / 加急付费 | 源代码+说明书 | **产品验证通过后启动** |
| App 备案 | 1~2 周 | ICP 备案完成 | 通过云厂商备案系统提交 |
| Apple Developer | 即时 | $99/年 | iOS 上架 |
| 安卓商店上架 | 各 1~2 周 | 软著 + ICP/App 备案号 + 隐私政策 | 华为/小米/OPPO/vivo/应用宝 |
| App Store 上架 | 审核 1~7 天 | 隐私政策、相机权限用途说明 | 注意 4.3/2.1 常见拒审点 |

> DEMO 阶段分发方式：TestFlight（iOS）+ 各安卓商店内测分发（不受备案限制）。

---

## 八、仓库结构与部署

```
Mr.Sheven/
├── docs/  probe/                    # 既有
├── pyproject.toml                   # uv workspace，shared/pipeline/server 三包
├── shared/                          # models(SQLAlchemy)、config、llm 客户端、清洗/归一化工具
├── pipeline/                        # 离线批处理（入口 python -m pipeline.scheduler）
│   ├── crawler/  subtitle/  cleaner/  dedup/  llm/  normalize/
├── server/                          # FastAPI（入口 uvicorn server.app:app）
│   └── app/（api/ services/ cache/ ratelimit/）
├── app/                             # Flutter 工程
└── deploy/                          # docker-compose.yml、nginx、alembic/
```

部署：单机 Docker Compose 五容器（mysql、redis、api、scheduler、nginx），mysql 镜像用 `mysql:8.0`（自动跟随 8.0.x 最新补丁，裁决 C6）；凭证（cookies.txt、第三方条码 API Key、百炼/OCR Key）走 `.env` + `~/.secrets/`，纪律沿用 05 文档三条铁律。MVP 需要百炼 API Key（LLM 提取/对比/酒标匹配研判）与阿里云 OCR Key（裁决 C12）；ASR 仍留 V2。

---

## 九、里程碑计划（单人开发 + Claude Code 辅助，约 10~12 周）

| 阶段 | 周期 | 交付物 | 验收标准 |
|---|---|---|---|
| **P0 探针收尾 + 识别验证** | 第 1~2 周（✅ 2026-10-04 已完成） | 03 文档 Go/No-Go 结论；进口酒条码覆盖率测试（裁决 C10，**结论：不达标**）；OCR 中文背标真瓶验证（**通过**） | 9 视频抽取指标达标（召回率/字段准确率/幻觉率）；条码 API 覆盖率 ≥60% → **未达成，已按预案换通道：裁决 C12 转 OCR 背标主路径** |
| **P1 数据管道工程化** | 第 2~5 周 | MySQL 建表（Alembic）；crawler/subtitle/cleaner/dedup/llm/normalize 六模块；三个定时 Job | 2 博主 × 50~100 视频全链路跑通；review 表产出结构化记录；管道失败率 <10%；人工抽查 20 条抽取质量不低于探针水平；去重三层防线各有测试用例 |
| **P2 查询服务** | 第 5~7 周 | FastAPI scan API；**scan-label OCR API（裁决 C12）**：读光 OCR 接入 + LLM 提取 + 三档匹配 + 条码绑定回写；L1+L2 缓存；第三方条码 API（辅助通道）；限流+防穿透；落库回写 | 缓存命中 P95 <50ms；条码未命中全链路 <2s；**OCR 全链路 <5s、三档匹配抽检准确率 ≥90%、零跨款误绑**；空值 5min/非酒 7d/限流 429 三防线集成测试通过 |
| **P3 Flutter App** | 第 6~10 周（与 P2 部分并行） | 4 页 App（扫码/结果/反馈/设置）；四形态渲染 + SERIES 同系列标注；**拍背标入口与取景引导**（裁决 C12）；扫码/拍照真机调通 | iOS+Android 真机端到端：扫真实酒瓶 → 3s 内见结果；**拍背标 → 5s 内见结果**；无评测提示卡文案符合裁决 C3 |
| **P4 加固与 DEMO 发布** | 第 10~12 周 | 监控日报 Job；Patch Job 观测；内测分发 | 日报推送管道成功率/扫码命中率/LLM 失败率/第三方额度四项指标；TestFlight + 安卓内测分发可体验 |

> 合规备案（软著/ICP/App 备案）在产品验证通过后再启动（裁决 C11），不阻塞 DEMO 开发和内测分发。

---

## 十、监控与运维（MVP 轻量方案）

- **日报 Job**（每日 08:00）：聚合前一日指标推送（邮件或 Bark）：管道各状态数量、LLM 失败/重试率、扫码次数与命中率、NOT_FOUND Top20 条码（= 缺漏抓取优先级清单）、**OCR 识别成功率 / 三档匹配分布 / OCR+LLM 单次成本**（裁决 C12）、第三方 API 额度余量、cookies 健康检查（失效即告警，B站风控前兆）
- **日志**：结构化 JSON 日志，管道沿用 `[跳过] BVID: xxx` 风格便于 grep；FAILED/DISCARDED/拦截事件必须留痕可回溯
- Prometheus/Grafana 属过度设计，V2 再说

## 十一、成本估算（MVP 运行期，月）

| 项 | 金额 |
|---|---|
| 云服务器 2C4G | ~100 元 |
| 百炼 LLM（夜间跑批提取/对比 + 在线酒标匹配研判） | 50~150 元 |
| OCR（阿里云读光，按次计费，在线识别主路径，裁决 C12） | 20~100 元 |
| 第三方条码 API（辅助通道，万次级） | 10~50 元 |
| 域名/证书 | ~10 元（年付摊薄，HTTPS 用 Let's Encrypt 免费） |
| **合计** | **~250~450 元/月**（另 Apple 开发者 $99/年、软著加急费可选） |

## 十二、风险与开放问题

| # | 风险 | 缓解 |
|---|---|---|
| R1 | **识别命中率仍是商业生死线**（01 文档头号风险）：第三方条码库对进口酒覆盖≈0（C10 已实测证实） | 识别主路径转 **OCR 中文背标**（裁决 C12），闭集匹配保证"评过的必命中"；scan_log 缺漏反哺 + "催更"入口；barcode↔SPU 自增长绑定让重复扫描零成本命中 |
| R2 | ~~备案周期失控~~ | 已降级：先出 DEMO，备案后续再启动（裁决 C11）；开发期用 TestFlight/内测分发 |
| R3 | B站风控 / cookies 失效 / **API 限频** | 每 20 分钟仅爬 2 页（断点续爬）；随机延迟 30~60s；5 种 UA 轮换；被限频直接停止不硬刚；完整浏览器请求头（Cookie/Referer/Sec-Fetch）；cookies 健康检查告警；05 文档三条铁律。⚠️ 详见"爬虫限频策略"章节 |
| R4 | LLM 对比误判 is_duplicate 造成数据丢失 | 软丢弃（DUPLICATE_CONFIRMED/DISCARDED 只标状态不删数据），日报输出丢弃清单可人工撤销 |
| R5 | uk_mid_day_title 误拦合法视频（同天多 P 清洗后同名） | 拦截全部写日志；人工找回脚本按 title 原文复核 |
| R6 | SPU 归一化产生重复酒款分裂评测数据 | possible_dup_of 待合并队列 + 每周人工合并 10 分钟；别名表随运行自增长 |
| R7 | 法律合规 | 只存事实性信息（谁给哪款酒打几分）+ 短摘录 + 原文出处链接，不逐字搬运完整文案（01 文档纪律）；App 隐私政策声明条码扫描与相机（拍酒标）权限及数据收集范围（裁决 C12 后新增相机权限用途说明） |

## 十三、V2.0 预留位（本期不做，字段/结构已留）

年份/酒龄精细化（spu.vintage_year / age_years 已预留）· ~~OCR 拍酒标识别~~（**已提前进 MVP**，裁决 C12；V2 增强：取景框实时 OCR 预检 + 标准标签图像相似度通道）· **ASR 转写兜底**（等平台 AI 字幕覆盖率提升后）· 向量检索去重 · UGC 用户口感评价（反馈页数据已落库）· 评分演变史独立页面 · 多平台博主（抖音/小红书）· uni-app 编译小程序作流量侧门 · Prometheus 监控体系 · 合规备案（软著/ICP/App 备案）正式上架。
