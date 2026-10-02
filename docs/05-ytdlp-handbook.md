# yt-dlp 操作手册与踩坑记录

## 安装（Windows + uv）

```bash
uv tool install yt-dlp        # 装成全局 CLI（像 git），不进项目依赖
yt-dlp --version              # 验证；本项目实测版本 2026.8.19
```

> 为什么用 `uv tool install` 而不是 `uv add`：yt-dlp 在探针阶段是命令行工具，不是被 import 的库。
> ≈ Java 里装一个本机 CLI vs 往 pom.xml 加 dependency。将来管道要程序化调用时再加依赖。

## 常用命令速查（均在本项目实测）

```bash
# 元信息（--print 用字段模板取任意元数据）
PYTHONIOENCODING=utf-8 yt-dlp --print "%(title)s | %(uploader)s | %(duration_string)s" <URL>

# 列出可用字幕（danmaku=弹幕无用；ai-zh=B站AI字幕需登录态）
yt-dlp --cookies <cookies.txt> --list-subs <URL>

# 下载 AI 字幕（不下载视频本体）
yt-dlp --cookies <cookies.txt> --write-subs --sub-langs "ai-zh" --skip-download \
  -o "probe/<BV号>/%(id)s" <URL>

# 只下载音频（bestaudio 得 m4a，无需 ffmpeg；只有 -x 转码才需要 ffmpeg）
yt-dlp -f bestaudio -o "probe/<BV号>/audio.%(ext)s" <URL>
```

## Windows 注意事项

1. **中文标题乱码**：控制台默认 GBK，命令前加 `PYTHONIOENCODING=utf-8`
2. **ffmpeg 不需要装**：`bestaudio` 直接输出 m4a；dashscope / faster-whisper（PyAV）都能直接读
3. **"1080P 高码率需大会员"警告可无视**：我们不要视频画面
4. **BV 号是 12 位**（BV + 10 字符）：复制分享链接常多带字符，404 时先数位数

## 踩坑记录（按时间序）

| 现象 | 根因 | 解法 |
|---|---|---|
| `BV1Yjciz3EuE1` 报 404 | BV 号多复制了一个字符（13 位） | curl 验证 + 截短为 `BV1Yjciz3EuE` |
| 输出中文乱码 | 控制台 GBK | `PYTHONIOENCODING=utf-8` |
| `--list-subs` 只有 danmaku | AI 字幕在登录墙后 | 需登录态（cookies） |
| `--cookies-from-browser edge` 报 "Could not copy Chrome cookie database" | Edge 运行中锁库 | 完全退出浏览器（含后台驻留进程）后重试 |
| 关浏览器后报 "Failed to decrypt with DPAPI" | Chromium 127+ App-Bound Encryption，外部程序无法解密 cookie | **浏览器直读路线放弃**；Chrome 同样受影响，装 Chrome 无用；改走扩展插件导出 cookies.txt，或 Firefox（不受 ABE 影响） |

## Cookie 安全纪律（三条铁律）

1. **cookies.txt = B 站登录凭证**：只放仓库外（当前约定位置 `C:\Users\Sheven\.secrets\`），
   永不提交 git，永不粘贴到对话/文档里，只传路径
   - 教训：曾误放 `code-vine/secrets/`（未被 .gitignore 覆盖，差一次 `git add .` 就入库），已迁出
2. **探针结束即失效**：删除文件，或 B 站"账号安全"→ 退出其他设备（使旧 cookie 作废）
3. **登录态只做低频抓取**：高频爬会触发风控，波及账号

## 导出插件

- Edge/Chrome 扩展商店：**Get cookies.txt LOCALLY**（认准此名，山寨插件有窃取风险）
- 用法：登录 bilibili.com → 点插件 → Export → 保存到 `C:\Users\Sheven\.secrets\`

## 探针目标视频

- BV1Yjciz3EuE《侍酒师真实测评：70分的1855列庄佳得美～》
- UP 主：Vanka-葡萄船长 | 时长 6:27 | 品类：红酒（1855 列级庄波尔多）
- 物料：`probe/BV1Yjciz3EuE/audio.m4a`（5 MB）
