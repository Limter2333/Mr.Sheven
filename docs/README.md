# Mr.Sheven — 酒类评测速查项目

> 愿景：在商超拿起一瓶酒拍照，立刻看到多位 B 站酒类博主对它的评测结论（评分/倾向/原话摘录），辅助购买决策。
> 数据来源：后台管道自动抓取指定博主的 B 站视频 → 转写 → LLM 结构化抽取 → 人工审核 → 入库。
> 技术后端：全 Python（FastAPI + SQLAlchemy + MySQL 8.0）；客户端：Flutter 原生 App（iOS + Android）。

## 文档索引

| 文档 | 内容 |
|---|---|
| [01-requirements-feasibility.md](01-requirements-feasibility.md) | 需求拆解、三大子系统可行性、关键风险 |
| [02-product-decisions.md](02-product-decisions.md) | 已定产品决策：垂类品类、多博主聚合、数据模型 |
| [03-data-pipeline-guide.md](03-data-pipeline-guide.md) | 数据端探针实验五步实施指南（Schema、提示词、核对指标） |
| [04-asr-strategy.md](04-asr-strategy.md) | 转写方案对比（ASR 暂不启用，裁决 C8）：B 站 AI 字幕 / Qwen ASR / 本地 Whisper |
| [05-ytdlp-handbook.md](05-ytdlp-handbook.md) | yt-dlp 操作手册、Windows 注意事项、踩坑记录、cookie 安全纪律 |
| [06-implementation-plan.md](06-implementation-plan.md) | **项目实施方案总纲**：架构、技术栈（全 Python + Flutter 原生 App）、库表设计、管道/接口实施要点、里程碑与备案工作流 |

## 目录结构

```
Mr.Sheven/
├── docs/                    # 本套文档
└── probe/                   # 探针实验物料（转写文本、抽取结果、核对表）
    └── BV1Yjciz3EuE/        # 首个测试视频
        └── audio.m4a        # 已下载的音频（6:27）
```

## 当前进度（P1：代码开发完成，待探针验证）

- [x] 需求可行性分析与产品决策
- [x] 数据端实施方案设计
- [x] 工程实施方案定稿（06 文档）：全 Python 后端 + Flutter 原生 App，含冲突裁决（C1-C11）、库表、里程碑
- [x] yt-dlp 安装并验证（`uv tool install yt-dlp`，版本 2026.8.19）
- [x] 定位首个测试视频：**BV1Yjciz3EuE**《侍酒师真实测评：70分的1855列庄佳得美～》| UP 主：Vanka-葡萄船长 | 6:27（红酒）
- [x] 音频已下载至 `probe/BV1Yjciz3EuE/audio.m4a`
- [x] **项目代码开发**：数据管道六模块 + 查询服务 + Docker部署 + 缓存/限流 + 监控 + 测试
- [ ] 浏览器插件导出 B 站 cookies.txt（放仓库外，只告知路径）
- [ ] 用 cookie 验证该视频有无 AI 字幕；有 → 直接下载；无 → 跳过（裁决 C8：不做 ASR）
- [ ] 生成统一的 `transcript.json`（带时间戳转写文本）
- [ ] LLM 结构化抽取（探针阶段由 Claude Code 直接完成，不接 API）
- [ ] 人工核对抽取质量，统计召回率/字段准确率/幻觉率
- [ ] 核对通过的记录写入 SQLite
- [ ] 得出 Go/No-Go 结论，决定是否工程化
- [ ] **100 个进口酒条码覆盖率抽样测试**（裁决 C10，P0 阶段完成）

## 下一个动作（两条线并行）

1. **探针线**：用户导出 cookies.txt（Edge 扩展商店装 **Get cookies.txt LOCALLY**）→ 告知文件路径 →
   运行 `yt-dlp --cookies <路径> --list-subs` 验证 AI 字幕可用性。
2. **条码验证线**：收集 100 个进口酒条码（威士忌/金酒/红酒各约 33 个）→ 测试第三方条码 API 覆盖率 →
   判断是否需要加数据通道。

> 合规备案（软著/ICP/App 备案）暂不启动（裁决 C11），先出 DEMO 验证产品。
