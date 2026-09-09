# 全球热点情报采集系统——多层数据源实测报告

> **实测元信息**（所有状态码均为真实请求结果，非记忆断言）
> - 时间：2026-09-09 03:00–04:40 UTC｜出口 IP：206.237.3.180（香港，AS42960 数据中心）
> - User-Agent：`NewsResearchBot/0.1 (personal research)`；单次 GET、跟随 ≤5 跳、35s 超时、gzip
> - GDELT 按官方要求 6s 间隔串行、另做 60s 退避重试；累计约 **170 个真实请求**
> - 复现命令：`curl -A "NewsResearchBot/0.1 (personal research)" -sS -L --compressed -m 35 -w '%{http_code} %{content_type}\n' <URL>`
> - ⚠️ 数据中心 IP 与住宅 IP 结果可能不同（YouTube 间歇 404、GDELT 429、Reddit 429 受 IP 信誉影响明显）

**实测总览**：~120 个端点返回 200 有效内容；11 个确认死亡/停服（Reuters RSS 三连挂、AP RSS 401、CNN RSS 子域 TLS 断连、Bloomberg 无 feed 等）；6 个被 WAF/限速拦截（Cloudflare ×2、Reddit 429、GDELT 429、NYT sitemap 403、ISW 403）。

---

## 1. 全球新闻媒体 RSS

| 源 | 类型 | 端点（实测 URL） | 语言 | 实测状态/形态/条数 | 最新条目时滞 | 备注 |
|---|---|---|---|---|---|---|
| **Reuters** | rss | `https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml` | EN | **404** | — | 官方 RSS 已死；`/rssfeed/worldNews` 401；`/sitemap.xml` 401；robots.txt = `Allow: /plus/` + `Disallow: /`（整站禁爬） |
| Reuters 替代 | gnews | `https://news.google.com/rss/search?q=site%3Areuters.com%20when%3A1d&hl=en-US&gl=US&ceid=US:en` | EN | **200** XML | 最新 3.0h | 实测 **100 条/24h**，Reuters 覆盖最佳替代 |
| **AP News** | rss | `https://apnews.com/index.rss` | EN | **401** "Invalid client credentials" | — | 公共 RSS 已停服；hub 页 `https://apnews.com/hub/ap-top-news` 200（服务端渲染 HTML 可解析）；另用 GNews `site:apnews.com` |
| **BBC front** | rss | `https://feeds.bbci.co.uk/news/rss.xml` | EN | **200** XML, 35 条 | 0.3h | robots 声明 sitemap（见 §6） |
| BBC World | rss | `https://feeds.bbci.co.uk/news/world/rss.xml` | EN | **200**, 29 条 | 0.3h | P0 |
| BBC UK | rss | `https://feeds.bbci.co.uk/news/uk/rss.xml` | EN | **200**, 30 条 | 0.4h | |
| BBC Business | rss | `https://feeds.bbci.co.uk/news/business/rss.xml` | EN | **200**, 53 条 | 0.3h | |
| BBC Technology | rss | `https://feeds.bbci.co.uk/news/technology/rss.xml` | EN | **200**, 21 条 | 3.9h | |
| BBC Politics | rss | `https://feeds.bbci.co.uk/news/politics/rss.xml` | EN | **200**, 61 条 | 1.6h | |
| **CNN** | rss | `https://rss.cnn.com/rss/edition.rss` / `edition_world.rss` | EN | **000**（TLS unexpected EOF，子域已死） | — | `cnn.com/services/rss/` 已跳转首页、页面无 `<link rel=alternate>`；CNN 无官方 RSS。替代：GNews `site:cnn.com`、Bing News RSS |
| **Al Jazeera** | rss | `https://www.aljazeera.com/xml/rss/all.xml` | EN | **200** rss+xml, 25 条 | 0.6h | 分区 feed（`middleeast.xml`/`africa.xml`）已 404，仅剩 all.xml；P0 |
| **The Guardian** | rss | `https://www.theguardian.com/world/rss`（`/business/rss` `/technology/rss` `/politics/rss` `/us-news/rss`） | EN | **全部 200**（29–45 条） | 0.2–0.4h | news sitemap 见 §6；P0 |
| **DW** | rss | `https://rss.dw.com/rdf/rss-en-all` | EN | **200** RSS1.0(RDF), 134 条 | 0.1h | RDF 格式，feedparser 兼容 |
| DW 德文 | rss | `https://rss.dw.com/rdf/rss-de-all` | DE | **200**, 86 条 | 0.1h | |
| DW 中文 | rss | `https://rss.dw.com/xml/rss-chi-all` | ZH | **200**, 58 条 | 0.1h | |
| **NHK** | rss | `https://www3.nhk.or.jp/rss/news/cat0.xml` | JA | **200** 但最新条目 **757h 旧**（2026-08-08） | 已停更 | NHK 已基本停止 RSS 分发；NHK World 英文页 `nhkworld/en/news/` TLS 断连(000)、`nhkworld/en/news/rss/all.xml` 404。替代：GNews `site:nhk.or.jp` 或 `hl=ja` topic |
| **CNBC** | rss | `https://www.cnbc.com/id/100003114/device/rss/rss.html`（Top） | EN | **200**, 30 条 | 0.2h | 同模式：World=`id/100727362`、Business=`id/20910258`、Economy=`id/10001147`，均 200 |
| **Bloomberg** | — | （无 RSS） | EN | 探测 feed 路径 **404**；robots 禁 Google-Extended | — | 替代：Yahoo Finance RSS + CNBC + MarketWatch + Bing News `q=bloomberg` |
| **NYT** | rss | `https://rss.nytimes.com/services/xml/rss/nyt/World.xml` | EN | **200**, 50 条 | 0.1h | 同模式 Technology/Europe 等，均 200；⚠️ robots.txt 明文**禁止 TDM/数据挖掘**（见 §7） |
| **WaPo** | rss | `https://feeds.washingtonpost.com/rss/world` | EN | **200**, 15 条 | 2.9h | `/rss/home`、`/rss/technology` 404（分区不全） |
| Times of Israel | rss | `https://www.timesofisrael.com/feed/` | EN | **403**（Cloudflare 验证码页） | — | 替代：GNews `site:timesofisrael.com` |
| The Hindu | rss | `https://www.thehindu.com/news/international/feeder/default.rss` | EN | **200**, 30 条 | — | `/feeder/default.rss`（首页）亦 200 |
| SCMP | rss | `https://www.scmp.com/rss/4/feed`（China）/ `https://www.scmp.com/rss/91/feed`（World） | EN | **均 200**, 各 50 条 | 0.4h | |
| RT | rss | `https://www.rt.com/rss/news/` | EN | **200**, 53 条 | 1.7h | 地缘视角对照源 |
| TASS | rss | `https://tass.com/rss/v2.xml` | EN | **200**, 100 条 | 0.4h | |
| NPR | rss | `https://feeds.npr.org/1004/rss.xml`（World）/ `1019`（Tech） | EN | **均 200**（10 条） | 7.4h/14h | 更新慢，P2 |
| Sky News | rss | `https://feeds.skynews.com/feeds/rss/world.xml`（`home.xml` 亦 200） | EN | **200**, 10 条 | 2.8h | |
| CBS News | rss | `https://www.cbsnews.com/latest/rss/main`（`/world` 亦 200） | EN | **200**, 30 条 | 0.0h | 极新鲜 |
| ABC News | rss | `https://abcnews.go.com/abcnews/topstories` | EN | **200** XML, 25 条 | 1.6h | |
| NBC News | rss | `https://feeds.nbcnews.com/nbcnews/public/news` | EN | **200** RSS, 25 条 | 1.4h | 旧式 `id/3032091` 端点已 404 |
| France24 | rss | `https://www.france24.com/en/rss` | EN | **200**, 23 条 | 0.8h | |
| Euronews | rss | `https://www.euronews.com/rss` | EN | **200**, 50 条 | 0.3h | |
| Le Monde（法） | rss | `https://www.lemonde.fr/rss/en_continu.xml` | FR | **200**, 60 条 | 0.2h | |
| RFI（法/英） | rss | `https://www.rfi.fr/fr/general/rss` / `https://www.rfi.fr/en/rss` | FR/EN | **均 200**（22–23 条） | 0.4h/6.8h | |
| Anadolu | rss | `https://www.aa.com.tr/en/rss` | EN/TR | **200**, 30 条 | 5.5h | feed 标题土耳其语，内容含英文分区 |

## 2. 科技

| 源 | 类型 | 端点 | 语言 | 实测 | 时滞/备注 |
|---|---|---|---|---|---|
| HN Algolia（front_page） | api | `https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30` | EN | **200** JSON, 30 hits | 免 key；对象含 title/points/created_at/author |
| HN Algolia（最新故事） | api | `https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=30` | EN | **200** JSON | 秒级新鲜（实测 latest 03:09Z） |
| HN 官方 RSS | rss | `https://news.ycombinator.com/rss` | EN | **200**, 30 条 | 1.3h |
| hnrss.org（frontpage） | rss | `https://hnrss.org/frontpage` | EN | **200**, 20 条 | 1.3h |
| hnrss.org（搜索） | rss | `https://hnrss.org/newest?q=openai` | EN | **502** ×3 | 搜索端点不稳定 → 用 Algolia `search_by_date&query=` |
| GitHub Trending | page | `https://github.com/trending` | EN | **200** 服务端渲染 HTML | 实测可提取 `/owner/repo/stargazers` 链接，无需 JS；robots 无 trending 限制 |
| GitHub Blog | rss | `https://github.blog/feed/` | EN | **200**（仅 1 条，量少） | 107h |
| GitHub Changelog | rss | `https://github.blog/changelog/feed/` | EN | **200**, 10 条 | 0.6h |
| TechCrunch | rss | `https://techcrunch.com/feed/` | EN | **200**, 20 条 | 4.0h |
| Ars Technica | rss | `https://feeds.arstechnica.com/arstechnica/index` | EN | **200**, 20 条 | 5.5h |
| The Verge | rss | `https://www.theverge.com/rss/index.xml` | EN | **200**, 20 条 | — |
| Wired | rss | `https://www.wired.com/feed/rss` | EN | **200**, 50 条 | 6.1h |
| Engadget | rss | `https://www.engadget.com/rss.xml` | EN | **200**, 20 条 | 3.9h |
| The Hacker News | rss | `https://feeds.feedburner.com/TheHackersNews` | EN | **200**, 50 条 | 11.1h |
| KrebsOnSecurity | rss | `https://krebsonsecurity.com/feed/` | EN | **200**, 10 条 | 5.6h |
| BleepingComputer | rss | `https://www.bleepingcomputer.com/feed/` | EN | **403**（Cloudflare "Just a moment"） | 替代：THN/Krebs/GNews `site:bleepingcomputer.com` |
| arXiv API | api | `https://export.arxiv.org/api/query?search_query=cat:cs.AI+AND+cat:cs.LG&sortBy=submittedDate&sortOrder=descending&max_results=20` | EN | **200** Atom, 20 entries | 免 key；官方请求间隔 ≥3s |
| arXiv RSS | rss | `https://rss.arxiv.org/rss/cs.AI` | EN | **200** | 每日批量发布 |
| Product Hunt | rss | `https://www.producthunt.com/feed` | EN | **200** Atom | |
| Techmeme | page | `https://www.techmeme.com/` | EN | **200** 服务端渲染 HTML | robots 仅禁 `/goto/ /r/ /search/` 等，主页可抓；无 RSS |

## 3. 财经

| 源 | 类型 | 端点 | 语言 | 实测 | 备注 |
|---|---|---|---|---|---|
| CNBC Business/Economy | rss | `id/20910258`、`id/10001147`（同 §1 模式） | EN | **200** | |
| MarketWatch（Dow Jones 直连） | rss | `https://feeds.content.dowjones.io/public/rss/mw_topstories` | EN | **200**, 10 条 | 1.0h |
| MarketWatch（旧端点） | rss | `https://feeds.marketwatch.com/marketwatch/topstories/` | EN | **200**, 10 条 | 同数据，双保险 |
| Yahoo Finance（全站） | rss | `https://finance.yahoo.com/news/rssindex` | EN | **200**, 50 条 | 4.4h |
| Yahoo Finance（个股） | rss | `https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US` | EN | **200**, 18 条 | 0.2h；`s=` 可换任意 ticker，做「公司关键词→股价波动」联动 |
| Investing.com | rss | `https://www.investing.com/rss/news.rss` / `market_overview.rss` | EN | **均 200**, 10 条 | robots.txt 403（反爬）但 /rss 开放；低频使用 |
| FT | rss | `https://www.ft.com/rss/home` | EN | **200**, 9 条 | ⚠️ 付费墙：只收标题/摘要，绝不绕墙；免费 RSS 官方已不再宣传，随时可能关 |
| 美联储 | rss | `https://www.federalreserve.gov/feeds/press_all.xml` / `press_monetary.xml` | EN | **均 200** | 政府域，公共领域友好 |
| ECB | rss | `https://www.ecb.europa.eu/rss/press.html` | EN | **200**, 15 条 | 12.4h（按发布会节奏）；`rss/fmop.html`、`rss/mop.html` **404**（货币政策决策 feed 已撤）→ 利率决议日直接抓 ECB 页面 |
| BIS | rss | `https://www.bis.org/list/press_rss.rss` | EN | **404** | 无有效 RSS；改抓 `bis.org` press 页面（低频）或用 Fed/ECB 覆盖央行线 |
| OilPrice | rss | `https://oilprice.com/rss/main` | EN | **200**, 15 条 | 0.1h 极新鲜；`/rss/news` 404 |
| Bloomberg | — | 无 RSS（404 探测 + robots 证据） | EN | — | 用 Yahoo Finance + CNBC + Bing News 替代 |

## 4. 地缘政治 / 社会

| 源 | 类型 | 端点 | 语言 | 实测 | 评估 |
|---|---|---|---|---|---|
| **GDELT DOC API** | api | `https://api.gdeltproject.org/api/v2/doc/doc?query=protest&mode=artlist&maxrecords=75&format=json&timespan=1d` | 多语 | **429** ×5（6s 间隔 + 60s 退避均 429） | 429 正文："Please limit requests to one every 5 seconds"。数据中心 IP 配额被占满。语法（官方文档，本次未能跑通）：`query` 支持 `domain:reuters.com`、`sourcelang:eng`、`theme:...`；`mode=artlist/timelinevol/tonechart`；`format=json/xml`。**价值极高但需住宅 IP 或 ≥10min 低频 + 退避** |
| GDELT GEO API | api | `https://api.gdeltproject.org/api/v2/geo/geo?query=protest&mode=pointdata&format=GeoJSON&timespan=1d` | — | **404**（nginx 裸 404） | GEO 2.0 API 已下线；替代：直接解析 events export CSV 的 Geo 坐标列 |
| **GDELT 事件库** | api | `http://data.gdeltproject.org/gdeltv2/lastupdate.txt` | 多语 | **200** | 返回最新 15 分钟批次 zip（export/mentions/gkg 三件套，实测 03:30 批次）；每 15min 全量更新——**这是比 DOC API 更稳的热点底料**，zip 下载解压后 SQL/CSV 处理 |
| Wikipedia 时事门户 | page | `https://en.wikipedia.org/wiki/Portal:Current_events/2026_September_9` | EN | **200**（当日页 51KB HTML） | 结构化可行；更适合机读：`https://en.wikipedia.org/w/api.php?action=parse&page=Portal%3ACurrent_events%2F2026_September_9&prop=text&format=json`（**200** JSON，干净 HTML 片段）；每日 00:00 UTC 建新页 |
| **Reddit** | rss | `https://www.reddit.com/r/worldnews/.rss` | EN | **200** Atom（需描述性 UA） | ⚠️ `old.reddit.com/.rss` 返回欢迎页 HTML；`r/geopolitics/.rss` **429**；robots.txt=`Disallow: /` 全禁 + Public Content Policy：**非商用、自报 UA、严格限速（≥1 次/分钟/子版）** |
| ISW | rss | `https://www.understandingwar.org/rss.xml` | EN | **403**（nginx） | `/rss`、`/feed` 均跳转主页 HTML；无可用 RSS |
| ISW 替代 | sitemap | `https://understandingwar.org/sitemap_index.xml` → `post-sitemap6.xml` | EN | **均 200**，post-sitemap6 最新 lastmod=2026-09-08/09（当日） | 用 sitemap lastmod 做文章发现，robots 明确禁 AI 爬虫（GPTBot Crawl-delay 600s）——低频、自报 UA |
| UN News | rss | `https://news.un.org/feed/subscribe/en/news/all/rss.xml` | EN | **200**, 30 条 | 15.4h（工作日更新）；中文版 `zh/...` 同模式 200 |
| ReliefWeb | rss | `https://reliefweb.int/updates/rss.xml` | EN | **200**, 20 条 | 0.6h |
| ReliefWeb API | api | `https://api.reliefweb.int/v2/reports?appname=...&limit=5` | EN | **403**："not using an approved appname"；v1 **410**（已退役） | API 需向 ReliefWeb 申请 appname 审批；现阶段用 RSS 即可 |
| ACLED | api | `https://api.acleddata.com/acled/read` | — | **000**（TLS 直接断连，2 次） | 需注册 key + 非商用许可；且本网络无法直连。替代：GDELT events + ReliefWeb |

## 5. 视频 / 流媒体（只存元数据）

| 源 | 类型 | 端点 | 实测 | 关键发现 |
|---|---|---|---|---|
| **YouTube 频道 RSS** | rss | `https://www.youtube.com/feeds/videos.xml?channel_id=UC16niRr50-MSBwiO3YDb3RA`（BBC News）；Al Jazeera English=`UCNye-wNBqNL5ZzHSJj3l8Bg`；DW News=`UCknLrEdhRCp1aegoMqRaCZg`（ID 均已从 `youtube.com/@handle` 页面 `externalId` 字段核实） | **200**（首轮 404/500，重试即 200——**间歇性故障，必须退避重试×3**） | 15 entries/次；**含热度指标**：`<media:starRating count average>`（点赞星级）+ `<media:statistics views>`（浏览量）+ `<yt:videoId>` + 缩略图，只存元数据完全可行 |
| YouTube uploads 播放列表 | rss | `...?playlist_id=UU<同 channel 后缀>`（UC→UU 转换） | 首测 404（与频道 feed 同为间歇故障） | 与 channel feed 等价，不必单独轮询 |
| YouTube Trending | page | `https://www.youtube.com/feed/trending` | 200 但为 JS 重页面（`ytInitialData`） | 可解析但脆弱；用「频道 RSS + views 排序」替代更稳。⚠️ robots.txt：`Disallow: /feeds/videos.xml`（对全 UA）——频道 RSS 属于灰区，见 §7 |
| Vimeo | rss | `https://vimeo.com/channels/staffpicks/videos/rss` | **200**, 10 条 | `/channels/staffpicks/rss`（不带 /videos）404 |
| PeerTube | rss | `https://framatube.org/feeds/videos.xml`（实例级） | **200** | 搜索 API `https://framatube.org/api/v1/search/videos?search=news&sort=-publishedAt` 亦 **200** JSON |
| Rumble | — | `https://rumble.com/rss` | 跳转后返回 **HTML**（非 RSS） | 无公开 RSS；GNews/Bing `site:rumble.com` 替代 |
| Twitch | api | `https://api.twitch.tv/helix/streams` | **401**（缺 Client-ID） | 无 RSS；helix 需注册 App 免费拿 client-id + OAuth |
| Bilibili 官方 API | api | `https://api.bilibili.com/x/web-interface/popular?ps=20&pn=1` | **200** JSON（免登录） | 热门榜单含 aid/title/pic/owner/duration/stat——元数据齐备；`x/space/wbi/arc/search` 返回 `code:-403`（需 WBI 签名+cookie） |
| RSSHub 公共实例 | rss | `https://rsshub.app/bilibili/user/video/94697411` | **403**（官方声明：仅限测试，逐步对 feed 读取器限流） | 社区实例 `rsshub.rssforever.com` 实测 **503**；自建 RSSHub 需 Node+Redis+（部分路由）浏览器，**512MB 共享主机不可行**。B 站直接用官方 web API（上条） |

## 6. 发现渠道 / 元层

| 渠道 | 端点 | 实测 | 用法要点 |
|---|---|---|---|
| **Google News RSS（topic 版）** | `https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en` | **200**, 57 条，最新 1.9h | topic 码：WORLD/BUSINESS/TECHNOLOGY/SCIENCE/HEALTH/ENTERTAINMENT/SPORTS/NATION |
| GNews（中文） | `https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans` | **200**, 26 条 | 参数规则：`hl`=界面语言，`gl`=地理偏好，`ceid=地区:语言`（如 `US:en`、`CN:zh-Hans`、`TW:zh-Hans`、`JP:ja`）；三者不匹配时服务端自动纠正 |
| GNews（search 版） | `https://news.google.com/rss/search?q=site%3Areuters.com%20when%3A1d&hl=en-US&gl=US&ceid=US:en` | **200**, 100 条 | `q=` 支持 `site:`、`when:1d/12h`、`-排除词`；**这是 Reuters/AP/CNN/ToI 等已死源的标准替代通道**；注意 item `<link>` 是 news.google.com 跳转码，标题尾带 `- 源名`，需 302 跟随或记录跳转链接 |
| **Bing News RSS** | `https://www.bing.com/news/search?q=climate+change&format=RSS` | **200**, 12 条 | `&qft=sortbydate%3D%221%22` 可按时间排序（实测同 200）；item `<link>` 为 bing 跳转，**解码 `url=` 参数即原文**；含 `<News:Source>` 源名、`<News:Image>` 缩略图 |
| **Guardian news sitemap** | `https://www.theguardian.com/sitemaps/news.xml` | **200**，460 条 `<news:news>`，lastmod=当日 03:14Z | 分钟级全量新文章发现通道 |
| **BBC news sitemap** | `https://www.bbc.com/sitemaps/https-index-com-news.xml` → 3 个子文件 | **200**，子文件各 **999** 条 `<news:news>`，lastmod 分钟级 | `/sitemaps/https-index.xml` 404——路径必须从 robots.txt 的 `Sitemap:` 声明取 |
| **NYT news sitemap** | `https://www.nytimes.com/sitemaps/new/news.xml.gz` | **200**，607 条（注意：**扩展名 .gz 但实际未压缩**） | `sitemap.xml`（未 gz）403——robots.txt 声明的 .gz 路径才放行 |
| Reuters sitemap | `https://www.reuters.com/sitemap.xml` | **401** | 整站禁爬确认 |
| RSSHub 公共实例 | `https://rsshub.app/` | **403**（官方声明仅测试用） | 见 §5；结论：公共实例不可作生产依赖 |
| Wikinews | `https://en.wikinews.org/w/api.php?action=query&list=recentchanges&rclimit=20&format=json` | **200** | 实测最近 20 条变更全是用户页/杂项——**基本停滞，不作为数据源** |
| Wikidata SPARQL | `https://query.wikidata.org/sparql?query=<SPARQL>&format=json` | **200**（带描述性 UA） | 实体背景补全（人物/组织/地点）而非热点发现；官方要求描述 UA、限并发 1、超时 60s |

## 7. 优先级汇总表 + 分批轮询方案

优先级定义：P0=每轮必跑（10min）；P1=每 3 轮（30min）；P2=每 6 轮（60min）。

### 7.1 源清单（轮询策略）

| 源 | 类别 | 类型 | 端点 | 语言 | 轮询 | 优先级 | 实测 |
|---|---|---|---|---|---|---|---|
| GNews topic WORLD | 元层 | gnews | `news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en` | EN | 10min | **P0** | 200 |
| GNews search Reuters | 元层 | gnews | `news.google.com/rss/search?q=site:reuters.com when:1d` | EN | 10min | **P0** | 200 (100条) |
| GNews 中文首页 | 元层 | gnews | `news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans` | ZH | 15min | **P0** | 200 |
| Al Jazeera all | 媒体 | rss | `aljazeera.com/xml/rss/all.xml` | EN | 10min | **P0** | 200 |
| BBC front | 媒体 | rss | `feeds.bbci.co.uk/news/rss.xml` | EN | 10min | **P0** | 200 |
| BBC World | 媒体 | rss | `feeds.bbci.co.uk/news/world/rss.xml` | EN | 10min | **P0** | 200 |
| Guardian World | 媒体 | rss | `theguardian.com/world/rss` | EN | 10min | **P0** | 200 |
| NYT World | 媒体 | rss | `rss.nytimes.com/services/xml/rss/nyt/World.xml` | EN | 15min | **P0** | 200 |
| CNBC Top | 媒体 | rss | `cnbc.com/id/100003114/device/rss/rss.html` | EN | 15min | **P0** | 200 |
| CBS main | 媒体 | rss | `cbsnews.com/latest/rss/main` | EN | 15min | P1 | 200 |
| AJ (YT 频道 feed) | 视频 | rss | `youtube.com/feeds/videos.xml?channel_id=UCNye-...` | EN | 30min | P1 | 200★ |
| BBC News (YT feed) | 视频 | rss | `...channel_id=UC16niRr50-MSBwiO3YDb3RA` | EN | 30min | P1 | 200★ |
| DW News (YT feed) | 视频 | rss | `...channel_id=UCknLrEdhRCp1aegoMqRaCZg` | EN | 30min | P1 | 200★ |
| UN News all | 地缘 | rss | `news.un.org/feed/subscribe/en/news/all/rss.xml` | EN | 30min | P1 | 200 |
| ReliefWeb updates | 地缘 | rss | `reliefweb.int/updates/rss.xml` | EN | 30min | **P0** | 200 |
| Reddit r/worldnews | 社区 | rss | `reddit.com/r/worldnews/.rss` | EN | 15min | P1 | 200⚠429风险 |
| GDELT lastupdate | 地缘 | api | `data.gdeltproject.org/gdeltv2/lastupdate.txt` | 多语 | 15min | P1 | 200 |
| Wikipedia 时事门户 | 地缘 | api | `wikipedia.org/w/api.php?action=parse&page=Portal:Current_events/当日` | EN | 60min | P1 | 200 |
| MarketWatch top | 财经 | rss | `feeds.content.dowjones.io/public/rss/mw_topstories` | EN | 10min | **P0** | 200 |
| Yahoo Finance rssindex | 财经 | rss | `finance.yahoo.com/news/rssindex` | EN | 15min | P1 | 200 |
| CNBC Business | 财经 | rss | `cnbc.com/id/20910258/...` | EN | 30min | P1 | 200 |
| OilPrice main | 财经 | rss | `oilprice.com/rss/main` | EN | 30min | P1 | 200 |
| Fed press_all | 财经 | rss | `federalreserve.gov/feeds/press_all.xml` | EN | 60min | P2 | 200 |
| ECB press | 财经 | rss | `ecb.europa.eu/rss/press.html` | EN | 60min | P2 | 200 |
| HN Algolia front_page | 科技 | api | `hn.algolia.com/api/v1/search?tags=front_page` | EN | 10min | **P0** | 200 |
| HN Algolia 最新 | 科技 | api | `hn.algolia.com/api/v1/search_by_date?tags=story` | EN | 10min | **P0** | 200 |
| arXiv cs.AI+LG | 科技 | api | `export.arxiv.org/api/query?...` | EN | 60min | P1 | 200 |
| GitHub Changelog | 科技 | rss | `github.blog/changelog/feed/` | EN | 60min | P2 | 200 |
| GitHub Trending | 科技 | page | `github.com/trending` | EN | 120min | P2 | 200 |
| TechCrunch / Verge / Wired / Engadget / Ars | 科技 | rss | （各自主 feed） | EN | 60min | P2 | 均 200 |
| THN + Krebs | 安全 | rss | `feedburner/TheHackersNews`、`krebsonsecurity.com/feed` | EN | 60min | P1 | 200 |
| RT + TASS | 地缘 | rss | `rt.com/rss/news/`、`tass.com/rss/v2.xml` | EN | 30min | P2 | 200 |
| SCMP China/World | 媒体 | rss | `scmp.com/rss/4/feed`、`/rss/91/feed` | EN | 30min | P1 | 200 |
| DW en/de/zh | 媒体 | rss | `rss.dw.com/...` | EN/DE/ZH | 30min | P1 | 200 |
| Le Monde + RFI | 媒体 | rss | `lemonde.fr/rss/en_continu.xml`、`rfi.fr/fr/general/rss` | FR | 60min | P2 | 200 |
| NHK(日) | 媒体 | rss | `www3.nhk.or.jp/rss/news/cat0.xml` | JA | ⚠️已停更 | P2→降级 | 200 但 757h 旧 |
| Guardian news sitemap | 发现 | sitemap | `theguardian.com/sitemaps/news.xml` | EN | 30min | P1 | 200 (460) |
| BBC news sitemap | 发现 | sitemap | `bbc.com/sitemaps/https-index-com-news.xml` | EN | 30min | P1 | 200 (3×999) |
| NYT news sitemap | 发现 | sitemap | `nytimes.com/sitemaps/new/news.xml.gz` | EN | 30min | P1 | 200 (607) |
| Bing News RSS | 发现 | rss | `bing.com/news/search?q=<词>&format=RSS` | 多语 | 按需 | P1 | 200 |
| Wikidata SPARQL | 元层 | api | `query.wikidata.org/sparql` | 多语 | 按需 | P2 | 200 |

★=需退避重试；⚠=受 IP 限速影响。

### 7.2 分片方案（cron 10–15min / 512MB / 20 进程上限）

- **规模**：P0 ≈ 15 源、P1 ≈ 15 源、P2 ≈ 12 源。
- **每轮成本**：P0 15 源 × 并发 5 × 平均 3s ≈ **<60s**，feedparser 峰值内存 <80MB——单轮毫无压力。
- **推荐 crontab 结构**（假设每 10min）：

```
*/10 * * * *  /home/bot/run.sh p0          # 每轮：15 个 P0 源，并发5
5,25,45 * * * *  /home/bot/run.sh p1       # 每 20-30min：P1 轮转一半
15 * * * *  [ $(date +%H) -le 23 ] && /home/bot/run.sh p1
20 */2 * * *  /home/bot/run.sh p2          # P2 每 2h
35 */3 * * *  /home/bot/run.sh sitemap     # news sitemap 批（Guardian/BBC/NYT）
50 */2 * * *  /home/bot/run.sh video       # YouTube feeds（3 频道，30-60min/次）
5 */6 * * *  /home/bot/run.sh slow          # GitHub trending / Fed / ECB / Techmeme
```

- **分片原则**：① 单进程内 httpx 异步并发 ≤6，全局超时 20s；② 同一域名每轮 ≤2 个请求；③ GDELT DOC API 单独跑且 ≥10min 间隔（或放弃 doc、只用 lastupdate+CSV）；④ ETag/If-Modified-Since 条件请求（BBC/Guardian/CNBC 均支持，304 时零解析成本）；⑤ feed 解析后立即释放，落 SQLite/文本。
- **重试规则（实测导出）**：YouTube feed 404/500 → 退避 10s 重试 ×3（实测第二次即 200）；Reddit 429 → 冷却 10min；GDELT 429 → 当轮放弃，60s 后单次重试，仍 429 则次日再试或换出口。

### 7.3 法律红线（按类）

| 类别 | 红线（本次实测证据） |
|---|---|
| 媒体 RSS | **Reuters** robots=`Disallow: /`（仅 /plus/ 例外）；**NYT** robots.txt 头部明文：禁止数据挖掘/TDM/AI/LLM 用途、禁缓存再分发——只收 RSS 标题+链接、注明出处；**FT/Bloomberg/WSJ** 付费墙：只取 headline+摘要，绝不绕墙或存全文 |
| robots 专项 | **YouTube** robots：`Disallow: /feeds/videos.xml`；**Reddit** robots：`User-agent: * Disallow: /` + Public Content Policy（非商用/自报UA/限速，r/reddit4researchers 通道）；**Google News** robots：`Disallow: /` 仅 Allow 首页/home/topics 等，`/rss/` 未在放行清单——以上三家均为「公开 feed 端点 vs robots 不放行」灰区：低频(≥10min)、少量、自报 UA、只存元数据、不二次分发全文 |
| 财经 | Yahoo ToS 禁止再分发与高频访问；Investing.com robots 403（仅 /rss 开放，勿扩面）；Fed/ECB 为政府机构出版物，风险低 |
| 地缘 | GDELT 免费+需署名；ReliefWeb 要求 appname + 署名 OCHA；Wikipedia/Portal 内容 CC BY-SA（署名+相同方式共享）；ACLED 需注册、非商用条款、禁再分发原始数据 |
| 科技 | GitHub robots 无 trending 限制但建议 ≤2h 一次；Techmeme 仅禁 /goto/ /r/ 等，主页可抓但属聚合体（链接回源头）；arXiv 官方要求 ≥3s 间隔 |
| 视频 | 见 7.4 |

### 7.4 视频源「只存元数据」合规要点

1. 只存：videoId、标题、channel_id/名、发布时间、时长、缩略图 URL、views/starRating 摘要、描述截断（≤200 字）——**不下载视频流/音频/字幕，不镜像完整描述**。
2. 缩略图用 YouTube CDN 原始 URL 热链或按需加载，不落地存储二次分发。
3. 频道数 ≤20、每频道 ≥30min 轮询、UA 自报；404 退避重试 ×3（实测必需）。
4. 不抓 Trending JS 页做主通道（脆弱+robots 边界）；用「频道 feed + views 排序」合成自己的热门榜。
5. Reddit 视频帖子只存 .rss 里已有的标题+链接+分数，不调用未授权 JSON API 扩面。

## 8. 降级 / 替代方案（实测失败源专项）

| 源 | 实测失败 | 已验证替代 |
|---|---|---|
| Reuters | `arc/outboundfeeds/rss` 404；`rssfeed/*` 401；sitemap 401；robots 全禁 | GNews `site:reuters.com when:1d`（200，100 条）；GDELT `domain:reuters.com`（语法见 §4） |
| AP News | `index.rss` 401 "Invalid client credentials" | `apnews.com/hub/ap-top-news`（200，服务端渲染 HTML 可解析）+ GNews `site:apnews.com` |
| CNN | `rss.cnn.com/*` TLS 直接断连（子域已死）；services/rss 跳转首页 | GNews `site:cnn.com`、Bing News RSS |
| Bloomberg | feed 路径探测 404；robots 禁 AI 爬虫 | Yahoo Finance rssindex + CNBC + MarketWatch + Bing `q=bloomberg` |
| NHK World 英文 | 站点 TLS 断连(000)、`nhkworld/en/news/rss/all.xml` 404 | GNews `site:nhk.or.jp` 或 `hl=ja` |
| NHK 日文 RSS | 200 但 757h 未更新（实质停更） | 同上 |
| Times of Israel | 403 Cloudflare 验证码 | GNews `site:timesofisrael.com` |
| BleepingComputer | 403 Cloudflare | The Hacker News（200）、KrebsOnSecurity（200） |
| WaPo | `/rss/home`、`/rss/technology` 404 | `/rss/world`（200）+ GNews `site:washingtonpost.com` |
| NBC 旧端点 | `id/3032091` 404 | `feeds.nbcnews.com/nbcnews/public/news`（200） |
| hnrss 搜索 | 502 ×3 | HN Algolia `search_by_date&query=` |
| ECB 货币政策 feed | `rss/fmop.html`、`rss/mop.html` 404 | `rss/press.html`（200）+ 决议日抓 ECB 新闻稿页面 |
| BIS | `list/press_rss.rss` 404 | bis.org press 页面低频抓取，或由 Fed/ECB 覆盖 |
| OilPrice news | `/rss/news` 404 | `/rss/main`（200） |
| Al Jazeera 分区 feed | `middleeast.xml`、`africa.xml` 404 | `all.xml`（200）+ GNews topic |
| ReliefWeb API | v1=410 退役；v2=403 需审批 appname | `reliefweb.int/updates/rss.xml`（200）；需要结构化再申请 appname |
| ACLED | TLS 断连 + 需 key | GDELT events CSV（200）+ ReliefWeb |
| GDELT DOC API | 429 ×5（含 60s 退避） | `data.gdeltproject.org/gdeltv2/lastupdate.txt`（200）→ 下载 export/gkg zip 自行索引；或住宅网络调用 doc API |
| GDELT GEO API | 404（已下线） | events export CSV 自带 Geo 坐标列 |
| ISW | `/rss.xml` 403；`/rss` `/feed` 跳主页 | `understandingwar.org/sitemap_index.xml`→`post-sitemap6.xml`（200，lastmod 当日） |
| Reddit r/geopolitics | 429 | r/worldnews/.rss（200）；子版轮换 + 冷却 |
| old.reddit RSS | 返回欢迎页 HTML | 仅用 `www.reddit.com/<sub>/.rss` |
| RSSHub | 官方 rsshub.app 403（仅测试声明）；rssforever 503 | B 站官方 web API `api.bilibili.com/x/web-interface/popular`（200）；自建 RSSHub 在 512MB 不可行（Node+Redis+浏览器） |
| Bilibili 用户投稿 API | `wbi/arc/search` code:-403（需签名） | popular/regional ranking API（免登录 200） |
| Rumble | `/rss` 返回 HTML | GNews/Bing `site:rumble.com` |
| Twitch | helix 401 无 key | 注册免费 App 取 client-id + OAuth；无 RSS |
| YouTube feed 首测 | 404/500 间歇 | 退避重试 ×3（实测重试即 200） |
| NYT sitemap 索引 | `sitemap.xml` 403 | robots 声明的 `sitemaps/new/news.xml.gz`（200，注意实际未 gzip） |
| BBC sitemap 索引 | `/sitemaps/https-index.xml` 404 | robots 声明的 `sitemaps/https-index-com-news.xml`（200） |
| Wikinews | 基本停滞（recentchanges 均用户页） | Wikipedia 时事 Portal API（200） |
| Vimeo | `/channels/staffpicks/rss` 404 | `/channels/staffpicks/videos/rss`（200） |

### 经验法则（从实测提炼）
1. **robots.txt 的 `Sitemap:` 行是金矿**：NYT/BBC/ISW 的有效 sitemap 路径都只写在 robots 里，猜路径必 404/403。
2. 大厂 feed 会**间歇性 404/500**（YouTube/Cloudflare 层）：统一加「退避重试 ×3 + 当轮放弃」逻辑。
3. 数据中心 IP 是最大变量：GDELT 429、Reddit 429、Cloudflare 拦截（ToI/BleepingComputer）都与 IP 信誉相关；同一代码从住宅/办公网络跑结果会更好。
4. feedparser 完全覆盖本次所有 200 源的格式（RSS 2.0/Atom/RSS1.0 RDF/JSON feed）。
