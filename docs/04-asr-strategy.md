# 转写（ASR）方案对比与决策

> ⚠️ **当前状态：ASR 暂不启用**（裁决 C8，见 06 文档）。MVP 阶段字幕失败直接跳过，不做 ASR 强攻。以下方案留作参考，等平台 AI 字幕覆盖率提升后再启用。

## 决策：三级通道（V2 参考）

1. **B 站 AI 字幕**（有则优先）：免费、干净、逐句时间戳；覆盖率不确定（取决于 UP 主设置）
2. **Qwen ASR 云端**（主力兜底）：qwen3-asr-flash 系列，中文专名强、支持 context 词表纠偏
3. **本地 faster-whisper**（最后备胎）：零费用但吃本机算力，云通道故障或成本失控时启用

## 方案对比

| 维度 | B 站 AI 字幕 | qwen3-asr-flash（云） | faster-whisper（本地） |
|---|---|---|---|
| 费用 | 免费 | ~0.79 元/小时音频 | 0 元，但耗 CPU/GPU 和时间 |
| 时间戳 | 有（逐句 from/to） | filetrans 版固定开启（句级/字级） | 有 |
| 中文酒名准确率 | 好 | 好（LLM-based ASR + context 纠偏） | 中（依赖 initial_prompt 调教） |
| 接入成本 | 需登录态 cookies.txt | API Key + dashscope SDK | 下载 ~3GB 模型 + 调参 |
| 依赖风险 | B 站接口/风控变动 | 限流、服务可用性 | 完全自主 |

## Qwen ASR 关键事实（调研于 2026-10）

- **计费**：按音频时长，约 0.00022 元/秒 ≈ 0.79 元/小时（国际部署标价，以百炼控制台为准；
  新用户通常有免费额度）
- **成本测算**：单视频（6.5 分钟）≈ 0.09 元；探针 9 视频 ≈ 1.6 元；
  全量库 1000 视频 × 20 分钟 ≈ 260 元；日常增量 ≈ 10 元/月 → **成本可忽略**
- **两个模型变体，务必用对**：
  - `qwen3-asr-flash`（同步）：单次限 5 分钟音频、**不返回时间戳** → 不适合本项目
  - `qwen3-asr-flash-filetrans`（异步，录音文件识别）：支持长音频、**时间戳固定开启**
    （`enable_words=false` 句级 / `true` 字级，单位毫秒）→ **本项目用这个**
    调用模式 = 提交任务 → 轮询结果（≈ Java 调异步作业服务）
- **context 参数**（酒名纠偏核心）：放 messages 最前面的 system 消息，上限 1 万 token，
  塞品牌词表/背景文本即可，无需预处理；仅 Qwen3-ASR-Flash 系支持
- **输入格式**：m4a 直接支持；本地文件走 `file://` 前缀 / Base64 / 公网 URL
- **SDK**：`pip/uv add dashscope`；API Key 放环境变量 `DASHSCOPE_API_KEY`（.env，不入库）
- **不确定点**：filetrans 对本地文件的提交方式（SDK 临时上传通道 vs 必须公网 URL）需实测；
  兜底：切段走同步版验证 context 效果，或用 Qwen3-ASR-Toolkit（GitHub 需走代理 SOCKS5 127.0.0.1:10808）

## B 站 AI 字幕要点

- 未登录时 `--list-subs` 只显示 danmaku（弹幕，无用）；登录后才可见 `ai-zh`
- 登录态获取：Edge/Chrome 127+ 的 App-Bound Encryption 导致 yt-dlp 无法解密浏览器 cookie
  （DPAPI 失败），**浏览器直读路线已死**；可行方案 = 扩展插件导出 cookies.txt（见 05）
- 字幕 JSON 每行含 `from`/`to` 秒数；也可在播放器 DevTools → Network 过滤 `subtitle`，
  手动拿 `aisubtitle.hdslb.com` 的 JSON
- 探针阶段顺手统计：所选博主视频中 AI 字幕覆盖率 → 决定 ASR 兜底比重

## 本地 faster-whisper 备忘

- PyAV 内置 ffmpeg 库，m4a 可直接读，无需另装 ffmpeg
- `initial_prompt` 塞词表纠偏，作用同 context
- 模型选 large-v3（中文最好）或 medium（省资源）

## 参考来源

- [非实时语音识别（Qwen-ASR）API 参考](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)
- [非实时语音识别用户指南](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)
- [qwen3-asr-flash 模型信息](https://help.aliyun.com/zh/model-studio/qwen3-asr-flash)
- [Qwen3-ASR 官方 Demo（context 用法）](https://huggingface.co/spaces/Qwen/Qwen3-ASR-Demo/blob/main/app.py)
- [Qwen3-ASR-Toolkit](https://github.com/QwenLM/Qwen3-ASR-Toolkit)
