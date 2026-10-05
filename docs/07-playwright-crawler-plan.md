# 07 - B站爬虫方案：WBI 签名 + Playwright 登录态

> 参考：[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 源码分析
> 修正：MediaCrawler 并非用浏览器拦截请求，而是 **Playwright 读密钥 + Python 计算 WBI 签名 + httpx 带签名发请求**

---

## 一、被限频的真正原因

| 问题 | 说明 |
|---|---|
| ❌ 之前以为 | httpx 直调被识别，需要用浏览器 |
| ✅ 实际原因 | **缺少 WBI 签名**，B 站拒绝未签名的 API 请求（-403 / -799） |

B 站 2023 年起对核心 API 启用 **WBI 签名机制**：
- 请求参数需附加 `wts`（时间戳）和 `w_rid`（签名哈希）
- 签名密钥（`img_key` + `sub_key`）存储在浏览器 `localStorage` 中
- 每天自动轮换密钥

未签名请求 → 拒绝（-403）或限频（-799）。

---

## 二、MediaCrawler 的真实架构

```
┌─────────────────────────────────────────────────┐
│  Playwright 浏览器（仅用于登录 + 读密钥）          │
│  1. 打开 bilibili.com，扫码/cookie 登录           │
│  2. 从 localStorage 读取 wbi_img_urls             │
│  3. 提取 img_key / sub_key（PNG 文件名即密钥）     │
│  4. 采集 Cookie 到 httpx session                  │
└──────────────────────┬──────────────────────────┘
                       │ 密钥 + Cookie
                       ▼
┌─────────────────────────────────────────────────┐
│  Python WBI 签名（纯算法，无需浏览器）             │
│  1. mixin_key = 置换表(img_key + sub_key)         │
│  2. wts = 当前时间戳                              │
│  3. params 排序 + URL编码 + 过滤特殊字符           │
│  4. w_rid = md5(query + mixin_key)                │
└──────────────────────┬──────────────────────────┘
                       │ 签名后的请求
                       ▼
┌─────────────────────────────────────────────────┐
│  httpx 发请求（带 WBI 签名 + Cookie + 浏览器头）   │
│  GET /x/space/wbi/arc/search?mid=xxx&pn=1        │
│       &ps=20&order=pubdate&wts=xxx&w_rid=xxx     │
└─────────────────────────────────────────────────┘
```

**限频策略（MediaCrawler 的做法）：**
- 每页请求间隔 `CRAWLER_MAX_SLEEP_SEC = 2` 秒
- 并发数 `MAX_CONCURRENCY_NUM = 1`（串行）
- 每日限量 `MAX_NOTES_PER_DAY = 1`
- 页大小固定 `ps = 20`（"bilibili limit page fixed value"）
- 失败重试指数退避：`5 * 2^attempt + random(0,1)` 秒

---

## 三、WBI 签名算法（纯 Python）

```python
import hashlib
import time
import urllib.parse
from functools import reduce

# 固定置换表（64 个索引位置）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

def get_mixin_key(img_key: str, sub_key: str) -> str:
    """从 img_key + sub_key 生成 mixin_key（置换后截取前 32 位）."""
    raw = img_key + sub_key
    return reduce(lambda s, i: s + raw[i], MIXIN_KEY_ENC_TAB, "")[:32]

def sign_params(params: dict, img_key: str, sub_key: str) -> dict:
    """为请求参数添加 WBI 签名 (wts + w_rid)."""
    mixin_key = get_mixin_key(img_key, sub_key)
    params["wts"] = int(time.time())
    
    # 按 key 排序，URL 编码，过滤特殊字符
    sorted_params = sorted(params.items())
    query = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote)
    # 过滤 !'()* 字符
    query = reduce(
        lambda s, c: s.replace(c, ""), "!'()*", query
    )
    
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid
    return params
```

---

## 四、实施架构

```
pipeline/crawler/
├── client.py           # 入库逻辑不变（save_videos / FetchResult / _clean_title）
├── wbi_sign.py         # 新增：WBI 签名算法
├── bilibili_client.py  # 新增：带签名的 API 客户端（替代 httpx 直调）
└── __init__.py
```

### 4.1 密钥获取（三种方式，优先级从高到低）

| 方式 | 来源 | 适用场景 |
|---|---|---|
| ① Playwright localStorage | `window.localStorage.wbi_img_urls` | 最可靠，MediaCrawler 首选 |
| ② nav API | `GET /x/web-interface/nav` → `wbi_img.img_url/sub_url` | 无需浏览器，但需要 Cookie |
| ③ 缓存文件 | `wbi_keys.json` | 密钥每天轮换，缓存 24h |

### 4.2 请求流程

```python
async def fetch_video_list_signed(mid: int, page: int) -> FetchResult:
    keys = await get_wbi_keys()  # 优先缓存 → nav API → Playwright
    
    params = sign_params({
        "mid": mid,
        "pn": page,
        "ps": 20,
        "order": "pubdate",
        "platform": "web",
        "web_location": "1550101",
    }, keys.img_key, keys.sub_key)
    
    resp = httpx.get(
        "https://api.bilibili.com/x/space/wbi/arc/search",
        params=params,
        headers=browser_like_headers,
    )
    # 解析 → FetchResult
```

### 4.3 依赖变更

```toml
# 新增（仅密钥获取需要，可选）
"playwright>=1.48.0",
# WBI 签名是纯 Python，无需额外依赖
```

---

## 五、限频策略（沿用 MediaCrawler 参数）

| 参数 | 值 | 说明 |
|---|---|---|
| 每页间隔 | 30~60 秒随机 | 我们的场景比 MediaCrawler 更保守 |
| 页大小 | 20 | B 站固定限制 |
| 并发数 | 1 | 串行请求 |
| 每轮页数 | 2 | 断点续爬 |
| 失败重试 | `5 * 2^attempt + random(0,1)` 秒 | 指数退避 |

---

## 六、实施步骤

1. **实现 `wbi_sign.py`**：纯 Python WBI 签名（无依赖）
2. **实现密钥获取**：先用 nav API（最简单），不够再加 Playwright
3. **实现 `bilibili_client.py`**：带签名的 `fetch_video_list`
4. **替换现有 `fetch_video_list`**：接口不变，内部切换
5. **测试验证**：确认 `code=0` 无限频
6. **集成 overnight_crawl**：保留限频追踪作为兜底

---

## 七、与之前方案的对比

| | 之前（httpx 无签名） | 之前（Playwright 拦截） | **现在（WBI 签名）** |
|---|---|---|---|
| 核心问题 | 缺 WBI 签名 | 过度设计 | ✅ 精准解决 |
| 资源占用 | 低 | 高（浏览器进程） | 低 |
| 实现复杂度 | 低 | 高 | **中** |
| 限频风险 | 高 | 低 | **低** |
| 浏览器依赖 | 无 | 必须 | 可选（仅密钥获取） |
