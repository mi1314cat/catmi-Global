# 自托管 / 免 API Key 的 Web Search 后端现状调查（2026-09）

> 调查日期：2026-09-09/10（所有"实测"均为本调查当天从一台**数据中心 IP** 的机器直接 `curl` 完成，与 Serv00 部署环境的 IP 属性一致，实测结论可直接外推）。
> 用途：Serv00 共享主机（512MB 内存 / 20 进程上限 / 3GB 磁盘 / 无 Docker / 无端口绑定 / 仅 Passenger node + cron python）上的 MCP Agent 搜索基础设施选型。
> 方法：web_search / advanced_search（bing / exa / tavily / keenable / ddg-lite）检索 + 对官方文档、GitHub 仓库源码、公共实例的**直接抓取与请求实测**。原文证据已存于 `/root/deepseek1/search-research/raw/`。

**置信度标注**：【官方文档】= 官方文档明确记载；【源码】= 官方仓库源码逐行确认；【实测】= 本调查 2026-09-09 从数据中心 IP 实际请求验证；【社区实测】= 第三方用户/项目报告；【推测】= 基于上述证据的推断。

---

## 1. SearXNG

### 1(a) 自托管最低资源消耗

| 数据点 | 数值 | 来源与置信度 |
|---|---|---|
| 官方文档 | **无任何最低 RAM/CPU 数字**（安装文档、Docker 文档均未给出） | 【官方文档】https://docs.searxng.org/admin/installation/installation-docker.html （本次抓取全文无 RAM 字样） |
| 官方 uWSGI 模板默认值 | `workers = ${UWSGI_WORKERS:-%k}`（默认 = CPU 核数）、`threads = ${UWSGI_THREADS:-4}` | 【源码】https://github.com/searxng/searxng/blob/master/utils/templates/etc/uwsgi/apps-available/searxng.ini |
| 社区实测（searxng 官方讨论区，4 核机器） | 默认 uWSGI（workers=%k=4）空载 **≈600MB**；改 `workers=1` 后 **≈150MB**；改用 `python -m searx.webapp` 裸跑 ≈ workers=1 水平 | 【社区实测】https://github.com/searxng/searxng/discussions/1892 |
| 社区 issue（2025-02） | `docker run --rm -it searxng/searxng` 空载 **>1.3GB**（默认模板在多核机 spawned 多 worker 所致） | 【社区实测】https://github.com/searxng/searxng-docker/issues/336 |
| 结论 | SearXNG 单 worker（workers=1、threads=1~2）空载 **≈150–250MB RSS** 是当前最可信的量级；Docker 默认配置在多核机上会放大到 0.6–1.3GB+ | 【社区实测+源码推断】 |

> Serv00 视角：512MB 内存跑一个 workers=1 的 SearXNG 理论可行，但 uwsgi master+worker ≈2 进程 + Flask 常驻，叠加 Agent 本体后余量很小。

### 1(b) 对 Redis（现为 Valkey）的依赖程度

- 官方文档：**"The limiter requires a Valkey database."**（limiter、botdetection 的动态 IP 列表、滑动窗口计数全部依赖 Valkey/Redis）【官方文档】https://docs.searxng.org/admin/searx.limiter.html
- Valkey 是 Redis 协议兼容分支，SearXNG 文档/源码已全部改称 `valkey:`，连接串形如 `valkey://localhost:6379/0`【官方文档】https://docs.searxng.org/admin/settings/settings_valkey.html
- **无 Valkey 能否运行：能，但有条件。** 源码 `searx/limiter.py::initialize()` 逐行确认：
  - `server.limiter: false` 且 `server.public_instance: false` 时，函数直接 return，**limiter 不安装、应用正常跑**；
  - 开了 limiter 但没有 Valkey → 仅记录 ERROR 日志后**继续运行（无 limiter）**；
  - 开了 `public_instance: true` 但没有 Valkey → `sys.exit(1)`，**拒绝启动**。【源码】https://github.com/searxng/searxng/blob/master/searx/limiter.py
- 官方 docker-compose 默认捆绑 `valkey/valkey:9-alpine` 容器【源码】https://github.com/searxng/searxng/blob/master/container/docker-compose.yml
- 已知坑：`server.public_instance: true` 会强制启用 limiter，导致 JSON API 被限流（见 1(d)）【社区实测】https://github.com/searxng/searxng/issues/2993
- 结论：**Valkey 是"limiter 的依赖"，不是 SearXNG 内核的依赖**。私有实例（limiter=false）无 Redis 可跑；代价是任何人都能高频打你的实例、把你的出口 IP 打进上游 CAPTCHA。

### 1(c) JSON API 是否默认开启、如何在 settings.yml 开启

- **默认不开启**。官方文档："If you want to consume the results as JSON, CSV, or RSS, you need to set the `format` parameter accordingly… Requesting an unset format will return a **403 Forbidden**. Be aware that many public instances have these formats disabled."【官方文档】https://docs.searxng.org/dev/search_api.html
- 默认 `settings.yml` 的 `search: formats:` 列表只有 `- html`【官方文档】https://docs.searxng.org/admin/settings/settings_search.html
- 开启方法（admin settings 文档）：

  ```yaml
  search:
    formats:
      - html
      - json      # ← 加这一行即开启
      # - csv
      # - rss
  ```
  【官方文档】https://docs.searxng.org/admin/settings/settings_search.html （"Result formats available from web, remove format to deny access (use lowercase)"）
- 第三方复现（2026-07-02 对公共实例逐个 curl 验证，含源码引用）：https://dev.to/wrencastellan/your-searxng-json-integration-works-on-your-own-instance-and-silently-breaks-on-everyone-elses-d7o 【社区实测】
- LiteLLM 文档同样提示 "the only active output format by default is the HTML format"【官方/第三方文档】https://docs.litellm.ai/docs/search/searxng

### 1(d) searx.space 现状与公共实例 JSON 实测

- **searx.space 官方快照（2026-09-09 04:20 UTC，https://searx.space/data/instances.json 直取）**：共 **92 个实例**（81 个 clearnet + 11 个 tor）；其中 54 个运行 2026.9.8 最新版【实测】。
- **本调查对全部 78 个可达 clearnet 实例逐个发 `GET /search?q=weather&format=json`（数据中心 IP、浏览器 UA）**，结果：
  - ✅ **返回真 JSON 的只有 2 个**：`https://search.mectov.my.id`（200，10 条结果，连发 3 次均 200 未触发限速）和 `https://sx.xo.st`（200，10 条结果）；两者均为 2026.9.x 新版本、searx.space checker 成功率 100%【实测】
  - ❌ 40+ 个返回 **429 Too Many Requests**（limiter ip_limit）
  - ❌ ~10 个返回 **200 但内容是 HTML**（JSON 未启用/前置了反代），含 baresearch.org、search.hbubli.cc、search.inetol.net、searxng.canine.tools 等【实测】
  - ❌ 403（JSON 未启用的标准报错）、418（反爬茶壶）、503/000（挂了）各若干【实测】
- **为什么 searx.space 显示 100% 成功而你却 429**：SearXNG 源码 `limiter.toml` 默认 `pass_searxng_org = true`，把官方 checker `check.searx.space` 的 IP 硬编码放行——checker 永远不被限流，普通客户端会被限【源码】https://github.com/searxng/searxng/blob/master/searx/limiter.toml
- **默认限速有多狠**：源码 `searx/botdetection/ip_limit.py`：**非 HTML 格式（即 API 请求）默认 `API_WINDOW=3600s / API_MAX=4` —— 每个 IP 每小时只允许 4 次 JSON 请求**；HTML 请求为 20 秒窗口 15 次 + 10 分钟窗口 150 次【源码】https://github.com/searxng/searxng/blob/master/searx/botdetection/ip_limit.py
- 社区佐证："Too many requests ONLY when using SearXNG programmically"【社区实测】https://github.com/searxng/searxng/issues/3537 ；"Live search returns 0 results: SearXNG instances rate-limit/forbid programmatic JSON queries"【社区实测】https://github.com/ChHsiching/agent-web-search/issues/10
- **限速政策小结（对 DC-IP 友好度）**：
  | 实例 | JSON | 数据中心 IP 表现 | 说明 |
  |---|---|---|---|
  | search.mectov.my.id | ✅ | 200，短时 3 连发未限速 | 2026.9.5，个人小实例，无 SLA【实测】 |
  | sx.xo.st | ✅ | 200 | 2026.9.8，个人小实例，无 SLA【实测】 |
  | etsi.me / opnxng.com / priv.au / searx.tiekoetter.com / paulgo.io 等 | ❌（429） | 第一发即 429 | limiter 默认 API 4 次/小时，或更高【实测】 |
  | baresearch.org / search.inetol.net 等 | ❌（200-HTML） | 返回 HTML 而非 JSON | JSON 未开或反代拦截【实测】 |
- **推论**：公共实例 JSON 路线在 2026 年已从"可用"退化为"碰运气"。列表站不能作为选型依据（pass_searxng_org 放行导致数据失真），必须逐个实测，且随时会变。

### 1(e) 搜索参数（准确参数名）

官方 Search API（GET/POST `/search` 均可）【官方文档】https://docs.searxng.org/dev/search_api.html ：

| 参数 | 取值 | 备注 |
|---|---|---|
| `q` | 任意查询串 | 必填；支持透传各上游语法（`site:` 等） |
| `categories` | 逗号分隔，如 `general`, `news`, `images`, `it`, `science`… | 本调查实测 `categories=news` → 8 条结果，全部来自 `bing news` 引擎【实测】 |
| `language` | 语言代码，如 `en`, `zh-CN`（默认取 `search:` 段默认值） | 实测 `language=zh-CN` → 9 条中文结果【实测】 |
| `time_range` | `day` / `week` / `month` / `year` | **注意文档滞后**：dev 文档页只写 `[day, month, year]`，但源码类型是 `Literal["day","week","month","year"]`，`week` 实际可用【源码】https://github.com/searxng/searxng/blob/master/searx/search/models.py |
| `pageno` | 1, 2, 3… | 分页 |
| `format` | `json` / `csv` / `rss` | 须在 `search: formats:` 中开启，否则 403 |
| `safesearch` | 0 / 1 / 2 | |
| `theme` | `simple` 等 | |

另有 `engines=`（指定引擎白名单）与 `durations` 等未列入上表的历史参数，属实例行为差异，不建议依赖【推测】。

---

## 2. mcp-searxng（GitHub 项目）

主项目 = **ihor-sokoliuk/mcp-searxng**（npm 包名 `mcp-searxng`，README 徽章自称 GitHub MCP Registry 收录）。

| 维度 | 事实 | 置信度/来源 |
|---|---|---|
| 架构 | **是 SearXNG 的 MCP 包装，且明确"不是 SearXNG 插件"**：README 原文 "Not a SearXNG plugin: This project cannot be installed as a native SearXNG plugin. Point it at any existing SearXNG instance… by setting `SEARXNG_URL`." 它把 MCP 工具调用翻译为对 SearXNG 实例 HTTP JSON API（`/search`、`/config`、`/autocompleter`）的请求 | 【官方文档】https://github.com/ihor-sokoliuk/mcp-searxng |
| 配置 | 核心变量 `SEARXNG_URL`（必需；支持分号分隔多副本：`https://a;https://b`，默认按序 failover，`SEARXNG_FANOUT=true` 并行 fan-out 合并去重）；支持 Basic Auth 内嵌 `https://user:pass@host`；另有 `SEARXNG_MAX_RESULTS / SEARXNG_TIMEOUT_MS / SEARXNG_DEFAULT_RESPONSE_FORMAT / SEARXNG_HTML_FALLBACK / SEARXNG_LITE_TOOLS / SEARCH_USER_AGENT / HTTP(S)_PROXY / NO_PROXY` 等 | 【官方文档】https://github.com/ihor-sokoliuk/mcp-searxng/blob/main/CONFIGURATION.md |
| 工具集 | `searxng_web_search`（分页/时间/语言/safesearch/min_score）、`web_url_read`（读单页转 Markdown，内置 SSRF 防护）、`searxng_search_suggestions`、`searxng_instance_info`（能力发现） | 【官方文档】README "Tools" 节 |
| 公共实例兼容 | 针对"公共实例拒绝 format=json"提供 `SEARXNG_HTML_FALLBACK=true`（403/非 JSON 时改抓 HTML 页解析标题/URL/摘要）与 FlareSolverr 支持 | 【官方文档】CONFIGURATION.md |
| 资源占用（官方实测快照 2026-07-29） | 单客户端 Small：52–111MiB 观测 / 建议 192–256MiB；4 客户端 Balanced：建议 256–384MiB；8 会话 Research-heavy：建议 512–768MiB | 【官方实测】https://github.com/ihor-sokoliuk/mcp-searxng/blob/main/docs/deployment-profiles.md |
| 维护状态 | **活跃**：created 2024-12-23，最近 push **2026-09-07**，v2.1.0，npm/Docker 双渠道分发 | 【实测·GitHub API】https://api.github.com/repos/ihor-sokoliuk/mcp-searxng |
| star / license | **1,214 stars**，**MIT**，158 forks | 【实测·GitHub API】同上 |
| 对公共实例的官方立场 | docs/public-searxng-instances.md 明确建议：单实例、关 fanout、先 `/config` 再一次小 JSON 搜索试探、别把公共实例当长期依赖；"Self-hosting SearXNG with JSON output enabled remains the recommended setup" | 【官方文档】https://github.com/ihor-sokoliuk/mcp-searxng/blob/main/docs/public-searxng-instances.md |

同位替代品（如主项目不合适）【实测·GitHub API】：
- SecretiveShell/MCP-searxng：128★，Python，MIT，push 2026-05-29 —— https://github.com/SecretiveShell/MCP-searxng
- jae-jae/searxng-mul-mcp：103★，TypeScript，**无 license 文件**，push 2025-08-25 —— https://github.com/jae-jae/searxng-mul-mcp
- OvertliDS/mcp-searxng-enhanced：54★，Python，MIT，push 2026-05-05 —— https://github.com/OvertliDS/mcp-searxng-enhanced

---

## 3. AgentSearch

- **是什么**：t0ken-ai/AgentSearch，自称 "The search engine for AI agents. 39+/100+ sites, zero API keys, zero cloud, zero cost. 100% local & private." 提供 CLI（`agentsearch search …`）、MCP server（`python -m agent_search.mcp_server`）与 HTTP API 三种形态；支持多引擎 fan-out（google/reddit/hackernews/arxiv…）与 SERP+正文一站式抽取【官方文档】https://github.com/t0ken-ai/AgentSearch
- **是否免 key**：是，零 API key（其核心卖点）；但**强依赖 CloakBrowser**——一个带 49 处 C++ 指纹补丁的 Chromium fork（`pip install "cloakbrowser[geoip]>=0.5.7"`），靠真实隐身浏览器直连 Google/Bing/Reddit 等绕 Cloudflare/PerimeterX/Akamai【官方文档】同上 README "The CloakBrowser Edge" 节
- **维护状态 / 成熟度**：created 2026-05-19，最近 push 2026-08-13；**2 stars、0 forks、未上 PyPI（`pypi.org/pypi/agentsearch` → 404，需 git 安装）**【实测·GitHub API + PyPI API】
- **结论**：技术路线（隐身 Chromium 直连）与 Serv00（512MB、无 Docker、进程受限）完全冲突；项目极年轻、无社区背书。**不适用本场景**【推测（基于上述硬事实）】

---

## 4. 其他免 Key 搜索路线（2026 现状）

> 总背景：微软 **Bing Search APIs 已于 2025-08-11 全线退役**（官方 Lifecycle 公告）——"免 key 拿 Bing 数据"从此只剩网页解析与 RSS 两条路。【官方文档】https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement ；【媒体报道】https://www.theverge.com/news/667517/microsoft-bing-search-api-end-of-support-ai-replacement

| 路线 | 端点 | 当前可用性（数据中心 IP） | 证据 |
|---|---|---|---|
| **DuckDuckGo HTML/Lite** | `https://html.duckduckgo.com/html/?q=…`、`https://lite.duckduckgo.com/lite/?q=…`（GET/POST 均试） | ❌ **HTTP 202 + CAPTCHA**（"Unfortunately, bots use DuckDuckGo too. Please complete the following challenge… Select all squares containing a duck"），HTML/Lite、GET/POST 三种姿势全部一样 | 【实测】本调查 2026-09-09 curl 直测；【社区实测】ddgs 库两年内多个 "202 ratelimit on DDGS" issue（2025-03、2025-05）https://github.com/deedy5/ddgs/issues ；"DuckDuckGo web search provider blocked by bot detection on datacenter IPs" https://github.com/can1357/oh-my-pi/issues/3863 ；Rust 生态直接把 `BlockReason::Http202` 做成枚举 https://docs.rs/crate/duckduckgo-core/latest |
| **Bing 网页版** | `https://www.bing.com/search?q=…&count=10` | ✅ 当前可解析：200，返回 10 个 `b_algo` 有机结果，无 CAPTCHA（浏览器 UA） | 【实测】本调查 curl 直测（123KB HTML/10 结果）；ddgs 库持续提供 `bing` 后端亦可佐证其可解析性 https://github.com/deedy5/ddgs 。注意：无官方 API（已退役）、布局可能变、偶发 consent/verify 页，属"软可用" |
| **Google News RSS** | `https://news.google.com/rss/search?q=…&hl=en-US&gl=US&ceid=US:en` | ✅ 可用且对 DC IP 友好：`q=deepseek when:1d` → 48 条 item；`q=deepseek after:2026-09-01 before:2026-09-10` → 100 条 item | 【实测】本调查 curl 直测（两查询均 200）；参数研究：https://www.newscatcherapi.com/blog-posts/google-news-rss-search-parameters-the-missing-documentaiton 、https://cloro.dev/blog/google-news-rss/ （2026-06："Google has never published a reference for the Google News RSS endpoint"）、时间范围语法 https://stackoverflow.com/questions/63371876/ 。参数：`q`（支持 `when:1d/7d/…`、`after:YYYY-MM-DD`、`before:…`、`site:…`）+ `hl`/`gl`/`ceid`。无官方文档、无限速承诺，勿高频 |
| **Bing News RSS** | `https://www.bing.com/news/search?q=…&format=RSS` | ✅ 可用：200 + 12 条 item（默认市场）；⚠️ 加 `setmkt=zh-CN` 会被 302 重定向到 Bing 首页（0 条），市场参数与 format=RSS 组合不可靠 | 【实测】本调查 curl 直测 |
| **Wikipedia opensearch API** | `https://en.wikipedia.org/w/api.php?action=opensearch&search=…&limit=5&format=json` | ✅ 完全可用：秒回 `["deepseek",["DeepSeek","DeepSeek (chatbot)",…],[…],[对应 URL]]` | 【实测】本调查 curl 直测；【官方文档】https://www.mediawiki.org/wiki/API:Opensearch （另见 API Etiquette：串行请求、别打满） |

**小结**：免 key 路线里，对数据中心 IP 最稳的是 **RSS 家族（Google News RSS / Bing News RSS / Wikipedia API）**；Bing 网页解析当前可用但属灰色地带；DDG HTML 端点对 DC IP 已死（除非住宅代理或隐身浏览器）。

---

## 5. 纯 Python 轻量 meta-search 候选（非 SearXNG 全家桶）

严格意义的"纯 Python 单文件"在维护中的项目里不存在；最接近"轻量、可当库导入、无数据库服务"的是以下两个最佳候选：

### 候选 1：ddgs（原 duckduckgo_search，deedy5/ddgs）—— 最佳"库"形态
- **star / license / 活跃度**：**2,941★**，**MIT**，v9.16.0（push 2026-08-26，活跃）【实测·GitHub API + PyPI API】https://github.com/deedy5/ddgs · https://pypi.org/project/ddgs/
- **定位**："A metasearch library that aggregates results from diverse web search services"——pip 即装、`DDGS().text(...)` 直接出结构化 dict，**无浏览器、无数据库**【官方文档】README
- **后端**：text: `bing, brave, duckduckgo, google, grokipedia, mojeek, startpage, yandex, yahoo, wikipedia`；news: `bing, duckduckgo, yahoo`；images: `bing, duckduckgo`【官方文档】README 后端表
- **参数**：`region="us-en"`、`safesearch="off"`、`timelimit`（`d/w/m/y`；news 仅 `d/w/m`）、`backend="auto"`（多后端自动轮换）、`page`【官方文档】README
- **依赖**：`click + primp（Rust 实现、带浏览器指纹伪装的 HTTP 客户端）+ lxml`，极轻【实测·PyPI metadata】
- **附带形态**：`pip install ddgs[mcp]` 自带 **MCP stdio server**（`ddgs mcp`）、`ddgs[api]` 自带 FastAPI 服务【官方文档】README
- **风险**：duckduckgo 后端从数据中心 IP 会被 202 挡（见第 4 节）；auto 模式会在后端间轮换绕压【社区实测】

### 候选 2：Argo（taxueseek/argo-search）—— 最佳"Agent 原生"形态
- **star / license / 活跃度**：**119★**，**MIT**，v2.8.6，push 2026-09-07（非常新但活跃）【实测·GitHub API】https://github.com/taxueseek/argo
- **定位**："给 AI Agent 用的多语言搜索基础设施"：语言检测 → 领域路由 → **150+ 引擎（YAML spec）**多路召回 → RRF 融合 → 证据快评（selection/absorption/freshness/共识打分），输出 Agent 可直接用的证据 JSON；**免费引擎优先，API key 全部可选**；缓存 = 内存 + SQLite（无需数据库服务）【官方文档】README
- **形态**：MCP server（12 tools，`npx github:taxueseek/argo`）、DSH 插件、**Python 库调用 `from search import super_search`**；可选依赖里直接用 **ddgs CLI 作为 10 个本地免 key 后端**【官方文档】README "依赖清单" 节
- **注意**：安装以 GitHub 为唯一真源（npm registry 上的 `argo-search@1.0.1` 是**非官方陈旧版**，作者已把 `package.json` 设 `private: true` 防误装）【官方文档】README 安装节

### 落选/参考项
- **search-engine-parser**（bisohns/search-engine-parser）：491★，aiohttp 抓多引擎 SERP；**无 license 文件**（法律上默认保留所有权利，商用集成有风险），更新频率一般【实测·GitHub API】https://github.com/bisohns/search-engine-parser
- **whoogle-search**（benbusby/whoogle-search）：11,579★，MIT —— Google 代理元搜索（单引擎），Python，轻量自托管，可作为"要 Google 质量但不想上全家桶"的替代参考【实测·GitHub API】https://github.com/benbusby/whoogle-search
- **araa-search**（Extravi/araa-search）：332★，AGPL-3.0，自托管 Google 元搜索前端【实测·GitHub API】https://github.com/Extravi/araa-search

---

## 6. Crawl4AI 与 Scrapling 的"读取单页"用法对比

### Crawl4AI（unclecode/crawl4ai）
- **star / license / 版本**：**82,001★**，Apache-2.0，v0.9.2（push 2026-09-08）【实测·GitHub API】https://github.com/unclecode/crawl4ai
- **是否必须异步**：**是**。核心 API 就是 `AsyncWebCrawler` + `await crawler.arun(...)` + `asyncio.run()`；文档页标题即 "AsyncWebCrawler — The core class for asynchronous web crawling"；无同步一等 API（另有 `crwl` CLI 兜底）【官方文档】https://docs.crawl4ai.com/api/async-webcrawler/
- **是否必须浏览器**：**是**。安装即要求 `crawl4ai setup` / `python -m playwright install --with-deps chromium`；`BrowserConfig(text_mode=True)` 只是"禁图片提速"，仍要起 Chromium【官方文档】https://docs.crawl4ai.com/api/parameters/ ；README Quick Start 同
- **内存/启动开销**：官方 Docker 服务版要求 **"At least 4GB of RAM"**；官方架构文档自述无池化时每个并发用户 **500–700MB**（三层浏览器池化后压到 50–70MB/用户，但那是为高并发服务设计的重型方案）【官方文档】https://github.com/unclecode/crawl4ai/blob/main/deploy/docker/README.md · https://github.com/unclecode/crawl4ai/blob/main/deploy/docker/ARCHITECTURE.md
- **读单页场景的结论**：为读一页而起 Chromium + async 事件循环 ≈ 数百 MB、秒级启动，**对 512MB 主机不成比例**【推断，基于官方数字】

### Scrapling（D4Vinci/Scrapling）
- **star / license / 版本**：**79,461★**，**BSD-3-Clause**，push 2026-09-04【实测·GitHub API】https://github.com/D4Vinci/Scrapling
- **三档 fetcher（官方选型表）**【官方文档】https://scrapling.readthedocs.io/en/latest/fetching/choosing.html ：
  | | Fetcher | DynamicFetcher | StealthyFetcher |
  |---|---|---|---|
  | 浏览器 | ❌ 无 | Playwright Chromium/Chrome | Playwright（stealth） |
  | 内存档位 | ⭐（最低） | ⭐⭐⭐ | ⭐⭐⭐ |
  | 用途 | 纯 HTTP 能搞定的页面 | JS 渲染页 | 有硬防护的页面 |
- **同步优先**：`StealthyFetcher.fetch(...)` / `Fetcher.get(...)` 都是**直接可调的同步类方法**，不需要 asyncio；同时全量提供 `AsyncFetcher/AsyncStealthyFetcher` 变体【官方文档】choosing.html + README
- **无浏览器读单页 = 默认形态**：`Fetcher` 基于 curl_cffi（可 `impersonate='chrome'` 伪装 TLS 指纹），解析核心仅依赖 lxml/cssselect/orjson 等，内存占用极小【实测·pyproject】https://github.com/D4Vinci/Scrapling/blob/main/pyproject.toml （core deps 无浏览器；`[fetchers]` extra 才含 curl_cffi/playwright/patchright）
- **StealthyFetcher 何时才需要浏览器**：只有当目标页是 JS 动态渲染、或存在 Cloudflare Turnstile/Interstitial 之类的硬反爬时才用；0.3.13 起其引擎由 Camoufox **换成 patchright（打补丁的 Playwright Chromium）**，Camoufox 降级为可选项（官方原文："This fetcher used a custom version of Camoufox as an engine before version 0.3.13, which was replaced by patchright"）【官方文档】https://scrapling.readthedocs.io/en/latest/fetching/stealthy.html ；Camoufox 自述内存约 200MB https://github.com/daijro/camoufox
- **加分项**：自带 MCP server（普通 HTTP/浏览器/stealth 三类抓取工具，页面经 CSS 收窄+去除注入文本后再交给模型）与 Agent skill【官方文档】https://scrapling.readthedocs.io/en/latest/ai/mcp-server.html
- **对比结论（读单页）**：Scrapling 胜出——同步、无浏览器默认路径、BSD-3、依赖极轻；Crawl4AI 是"为批量爬取 + LLM 语料流水线设计"的重装备，读单页属于杀鸡用牛刀【推断，基于双方官方文档数字】

---

## 7. 对 Serv00 部署的建议（四选一）

**约束回顾**【任务给定】：512MB 内存、20 进程上限、3GB 磁盘、无 Docker、无端口绑定权限、仅 Passenger node + cron python；要承载的是 MCP Agent 的搜索基础设施。

### 四个选项逐一裁决

**❌ 选项 A：SearXNG 部署在 Serv00 上**
- 需要 Flask 常驻进程 + uWSGI（或裸 webapp）+（认真用的话）Valkey；Serv00 没有 WSGI Passenger 通道，只能靠 cron/nohup 拉起常驻进程，属"打擦边球"，20 进程上限下 uwsgi master+worker 再叠 Valkey 已用掉 ~3 个进程额度。
- 内存上 workers=1 理论 150–250MB（第 1(a) 节），再加 Agent 进程（若用 mcp-searxng，官方建议档 192–256MiB，第 2 节）→ **512MB 双进程并跑必爆**。
- 私有实例不开 limiter 就得自己防滥用；开 `public_instance` 又强制要 Valkey（第 1(b) 节）。
- 结论：**技术上勉强、运维上不划算，不推荐**【推断，基于 1(a)/1(b)/第 2 节数据】。

**⚠️ 选项 B：公共 SearXNG 实例**
- 实测 92 个实例里只有 **2 个** JSON 开放且对 DC IP 友好，且默认 limiter 对 API 请求是 **4 次/小时/IP**（第 1(d) 节）；无 SLA、随时变化，mcp-searxng 官方文档也只把它定位为"评估用"。
- 结论：**只能当 fallback tier，不能当主基础设施**【实测】。

**✅ 选项 C：外部 VPS 自建 SearXNG（+ mcp-searxng 指过去）**
- 一台 1GB/$3–5 月的 VPS：SearXNG workers=1（150–250MB）+ Valkey（alpine，~10–20MB）+ 开 JSON，mcp-searxng（SEARXNG_URL 指向它）在 Serv00 或任何地方消费——这是 mcp-searxng 官方推荐形态，参数、分页、时间过滤、能力发现全部可用，一劳永逸。
- 结论：**愿意花小钱求稳就选它**；代价是月费与一条新的信任边界【推断 + 官方文档】。

**✅✅ 选项 D（推荐）：不上 SearXNG，自写 provider 层**
- 组合零成本端点 + 轻库，全部在第 4/5 节实测过：
  - **新闻**：Google News RSS（`q=… when:1d / after:… before:…`，实测 48–100 条/查询）+ Bing News RSS（`?q=…&format=RSS`，实测 12 条）【实测】
  - **百科/实体**：Wikipedia `action=opensearch`（实测秒回）【实测】
  - **网页通用**：**ddgs 库**（2941★ MIT，sync、无浏览器、可 `backend="bing,brave,mojeek,wikipedia,…" auto 轮换`，自带 MCP stdio server），或 mcp-searxng 指向 1–2 个实测存活的公共 JSON 实例作二级源【实测 + 官方文档】
  - **单页读取**：纯 httpx/Scrapling `Fetcher`（curl_cffi TLS 伪装、同步、无浏览器）；有硬防护的页面才升级 Scrapling `StealthyFetcher`（浏览器档）【官方文档】
- 为什么它最契合 Serv00：
  - **零常驻服务**：RSS/API 全是无状态 HTTP GET，Passenger node 进程内直接 fetch 即可（甚至不需要 Python）；python 部分按需 cron/子进程拉起，用完即退，20 进程上限毫无压力；
  - **零额外内存**：没有 uWSGI/Valkey/Chromium，单次搜索就是一个临时进程；
  - **免 key、无 SLA 依赖单点**：每类端点都是官方"门面级"端点（Google News RSS 多年稳定、Wikipedia API 有正式文档），比 92 选 2 的公共 SearXNG 稳得多；
  - **升级路径平滑**：provider 层留一个 `searxng` provider 接口，将来上 VPS（选项 C）只需换配置。

### 最终建议（一句话）
**主路线选 D（自写 provider 层：RSS 端点 + ddgs + Wikipedia + httpx/Scrapling-Fetcher 读页），把 mcp-searxng 指向实测存活公共实例作为可插拔的二级源；如果愿意每月花 $3–5，用选项 C（1GB VPS 上 SearXNG workers=1 + JSON 开启 + mcp-searxng）替代 D 中的"公共实例二级源"，是唯一能长期稳的 SearXNG 形态；A（SearXNG 上 Serv00）与 AgentSearch（隐身 Chromium 系）直接排除。**

### 风险清单（供实现时防御）
1. DDG HTML 端点对 DC IP 返回 202+CAPTCHA——**不要**把 DDG HTML 当免 key 依赖（除非有住宅代理）【实测】。
2. 公共 SearXNG 实例的 JSON 存活率是"92 选 2"且持续变化——代码里要按 mcp-searxng 官方建议做单实例保守配置 + 失败熔断，不要 fan-out 打公共实例【官方文档 + 实测】。
3. Bing 网页解析无契约保证；Bing News RSS 的 `setmkt` 与 `format=RSS` 组合会 302 跳首页——市场参数要么不传，要么实测后再传【实测】。
4. SearXNG 文档的 `time_range` 页面漏写 `week`，以源码 `Literal["day","week","month","year"]` 为准【源码】。
5. mcp-searxng 自身在 Small 档也建议预留 192–256MiB——在 512MB 的 Serv00 上不要与 Agent 主进程并跑，更适合作为外部 VPS 方案的一部分【官方实测】。

---

## 附：本次实测方法说明（可复现）

```text
# 公共实例 JSON 扫描（2026-09-09，数据中心 IP）
for u in $(curl -s https://searx.space/data/instances.json | jq -r '...'); do
  curl -s --max-time 8 -A "Mozilla/5.0 ..." -o body.json -w "%{http_code}|%{content_type}" "$u/search?q=weather&format=json"
done
# 结果：78 个 clearnet 实例中 2 个返回 application/json（search.mectov.my.id、sx.xo.st）

# 免 key 端点直测（同日同 IP）
curl -s "https://html.duckduckgo.com/html/?q=test+query"        # → 202 + duck CAPTCHA
curl -s "https://www.bing.com/search?q=test+query&count=10"     # → 200, 10×b_algo
curl -s "https://news.google.com/rss/search?q=deepseek%20when:1d"                       # → 200, 48 items
curl -s "https://news.google.com/rss/search?q=deepseek%20after:2026-09-01%20before:2026-09-10"  # → 200, 100 items
curl -s "https://www.bing.com/news/search?q=deepseek&format=RSS" # → 200, 12 items
curl -s "https://en.wikipedia.org/w/api.php?action=opensearch&search=deepseek&limit=5&format=json"  # → 200
```
原始响应与抓取的文档/源码均存档于 `/root/deepseek1/search-research/raw/`。
