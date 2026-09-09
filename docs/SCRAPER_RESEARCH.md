# SCRAPER_RESEARCH — Scrapling 与 Crawl4AI 深度研究

> 研究日期: 2026-09-09 · 目标环境: s12.serv00.com (FreeBSD 14.3 / Python 3.11.13 / 512MB RAM / 20 进程 / 无 root / 无 Docker)
> 方法: GitHub/PyPI/官方文档核查 + 服务器真机实测（见 `~/news-lab/results/` 与 SCRAPER_BENCHMARK.md）
> 结论先行: **Scrapling 解析层可用且优秀；HTTP Fetcher 取决于 curl_cffi 源码编译（实测中）；Crawl4AI 在 FreeBSD 上不可运行（证据链完整）；JS 重度站点用远端渲染/站点规则/放弃三级策略。**

---

## 1. Scrapling（D4Vinci/Scrapling）

### 1.1 版本与活跃度
- 最新 **0.4.15**（2026-08-23 发布），月度发版，活跃维护；PyPI 分类仍为 Beta；BSD-3-Clause；Python ≥3.10。
- 主包 wheel 为纯 `py3-none-any`（180KB）——本体安装零平台风险。

### 1.2 架构
| 组件 | 作用 | 依赖 | FreeBSD 可用性 |
|---|---|---|---|
| `Selector`（原 Adaptor） | lxml 解析器：CSS/XPath/BS4 风格查找、导航 | lxml, cssselect, orjson, tld, w3lib | ✅（lxml 系统预装 5.4.0；orjson 需 Rust——本机有 rustc 1.95） |
| `Fetcher`/`AsyncFetcher` | HTTP 抓取引擎 = **curl_cffi**（TLS 指纹伪装、HTTP/3） | curl_cffi（捆绑 libcurl-impersonate） | ⚠️ 需源码编译，实测中 |
| `DynamicFetcher` | Playwright + Chromium 浏览器自动化 | playwright | ❌ 无 FreeBSD wheel/sdist（PyPI 核查：0 sdist） |
| `StealthyFetcher` | patchright（改版 Playwright），可解 Cloudflare Turnstile | patchright | ❌ 同上 |

### 1.3 关键能力（与新闻管道对照）
- **自适应元素定位（auto-match）**：纯解析层特性，**不需要浏览器**。Save 阶段把元素唯一特征（标签/文本/属性/兄弟/路径）按 domain+identifier 存入 **SQLite**；Match 阶段按相似度打分重定位（默认阈值 40%，无匹配时告警）。→ 与"网站适配器自动学习"需求直接对应，且天然可回退（匹配不到就回退默认提取器）。
- **Fetcher 能力**：`stealthy_headers` 默认开（真实浏览器头）、`impersonate`（chrome/firefox/safari/edge 随机轮换）、`http3`、cookies、代理/代理轮换、`retries=3`+`retry_delay`、timeout 30s、`follow_redirects="safe"`（SSRF 防护）、`FetcherSession` 持久会话（sync+async）。
- **文本提取**：`get_all_text()`、`::text/::attr()`、正则助手；`Response.markdown(main_content_only=True)`（`[rag]` extra，markdownify）可去脚本/样式/**提示注入**——对新闻正文有直接价值。
- **图片提取**：**没有**专用 og:image/srcset 帮手，需要自写（我们已有 image_extract_test.py 的实现）。`LinkExtractor` 仅覆盖链接。
- **性能**：官方基准 5000 元素文本提取 1.99ms（≈裸 lxml，快 PyQuery 12×）；相似度搜索 2.31ms（AutoScraper 12.58ms）；无公开内存数据（自评 Fetcher 内存评级最高）。
- **并发**：`AsyncFetcher` + anyio Spider 框架（并发/AutoThrottle/暂停恢复），单进程——适配 20 进程上限。

### 1.4 FreeBSD 安装路径（实测验证中）
1. 纯解析层：lxml（系统已有）+ orjson（Rust 编译，本机 rustc 1.95 可用）+ 4 个纯 Python 包 → **预期成功**。
2. `pip install "scrapling[fetchers]"` → **预期失败**：playwright/patchright 无 FreeBSD wheel 且**无 sdist**（PyPI simple index 核查），pip 解析阶段直接失败。
3. `pip install curl_cffi` 单独装 → 需编译捆绑的 libcurl-impersonate，无 FreeBSD 官方文档路径（无 port）——**实测验证中，结果写入 BENCHMARK**。

### 1.5 结论（回答"能否作为主力采集引擎"）
- **解析层（Selector/自适应/markdown）**：可以，且是网站适配器自动学习的关键依赖。
- **HTTP 层**：若 curl_cffi 编译成功 → 完全可作主力（轻量、单进程、内建重试/代理/TLS 伪装）；若失败 → 降级方案：**httpx（系统已装 0.28.1）做 HTTP 层 + Scrapling 做解析层** 的组合，能力损失仅 TLS 指纹伪装。
- **浏览器层（Dynamic/Stealthy）**：本机不可用；如未来需要，走远端 CDP（`cdp_url`）或外部渲染服务。

---

## 2. Crawl4AI（unclecode/crawl4ai）

### 2.1 版本与活跃度
- 最新 **v0.9.3**（2026-08-31，安全修复版），Apache-2.0，Python ≥3.10，~82k stars，活跃。

### 2.2 FreeBSD 不可运行的证据链（全部实测/官方来源核查）
1. `pip install crawl4ai` 硬依赖 `playwright>=1.49` + `patchright>=1.49` + `playwright-stealth`；**playwright 在 PyPI 只有 manylinux/macosx/win wheel，0 个 sdist** → FreeBSD 上 pip 解析直接失败（无源可编）。
2. 即便从源码装，setup.py 按 `sys.platform` 过滤 bundle，`freebsd14` 不匹配 → assert 失败；捆绑的 node driver 是 glibc Linux 二进制。
3. 唯一 FreeBSD 打包路径 `www/py-playwright` port **需要 Linuxlator（linux.ko + linux_base-rl9，root 权限）**，且 port 文档标注 Chrome 当前 broken（FreeBSD bug 289285）。
4. 即使全部装上：单个 headless Chromium 报告 200-400MB RSS + Python 进程（litellm/numpy）——社区实测单次运行吃 >1GB（Reddit）；已知内存泄漏 issue #1608（8GB 主机 5 并发即泄漏）；Chromium 进程树（zygote/GPU/network）会瞬间击穿 512MB + 20 进程双限。

### 2.3 浏览器无关模式？
v0.9.3 代码内存在 `AsyncHTTPCrawlerStrategy`（aiohttp 纯 HTTP，"optimized for memory efficiency"），但**官方文档未收录、代码内仅一处单测引用、模块级 import playwright 使其在无 playwright 环境根本无法 import**——不可用（除非 --no-deps + 伪造 stub 的 hack，未验证，不推荐）。

### 2.4 功能盘点（若环境允许时仍有价值）
fit_markdown（Pruning/BM25）、JsonCss/JsonXPath 无 LLM 结构化抽取、LLMExtractionStrategy（litellm）、BFS/DFS/Best-First 深爬 + 过滤/评分器、`arun_many` 内存自适应调度器 + 限速、SQLite 缓存、截图/PDF、媒体抽取（srcset/picture）、断点恢复（resume_state）。

### 2.5 结论（回答"是否适合 Serve00 长期运行"）
**不适合，且无法安装**——这不是资源调优问题，是平台根本不兼容。
替代策略（按优先级）：
1. **HTTP-only 采集为主**（覆盖绝大多数新闻站点——新闻站基本是 SSR）；
2. JS 重度站点：**站点专用规则**（直接打 XHR/JSON 接口）或**外部渲染服务**（远端 CDP / 自建 Linux VPS 上跑 Crawl4AI API，本机只发 HTTP 请求取渲染结果）；
3. 都不行 → 放弃该源（记录，不硬爬）。

---

## 3. 两者组合可行性（§15/§16 的回答）

理想架构 "Scrapling 轻量 HTTP + Crawl4AI 动态页" **在 Serve00 上退化为**：

```
Fetch Strategy
├── S1 RSS/Atom (feedparser, 系统已装)         ← 零成本，主力发现渠道
├── S2 HTTP+规则 (httpx/curl_cffi + trafilatura) ← 主力抓取
├── S3 Scrapling 解析 + 自适应重定位            ← 正文/选择器稳定性层
├── S4 站点专用规则 (sites/*.py + XHR/JSON)      ← JS 重度站点的替代方案
└── S5 外部渲染服务 (远端 Crawl4AI/CDP, 可选)    ← 未来扩展位, 默认关闭
```

是否启用 curl_cffi 还是 httpx、以及 S5 是否值得开，由 SCRAPER_BENCHMARK.md 实测数据决定（见 DECISIONS）。
