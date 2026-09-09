# SOURCE_STRATEGY — 多层数据源策略（全部经实测验证）

> 实测基础: 约 170 个真实 HTTP 请求（2026-09-09, 出口 = s12.serv00.com 同等网络环境）
> 完整逐端点数据: `SOURCE_PROBE_FULL.md` + `SOURCE_PROBE_results.tsv`（原始状态码/Content-Type/大小）
> 当前部署: `news/sources.seed.json`（49 源, 全部 kind 适配）

## 1. 优先级分层与轮询分片

| 层 | 频率 | 覆盖 |
|---|---|---|
| **P0**（每轮, 600-900s） | 10-15min | GNews WORLD / site:reuters.com / 中文 / BUSINESS, BBC world, Guardian world, AJ, DW, NYT world, CNBC top, MarketWatch, ReliefWeb, HN Algolia FP |
| **P1**（每 2-4 轮, 1800-3600s） | 30min-1h | BBC business/tech, Guardian tech, 3 家 News Sitemap, Bing News, Reddit worldnews, UN News, SCMP, ToI, CNBC world/economy/business, Yahoo Finance, THN, Ars/Verge/TechCrunch/Wired/Engadget, YouTube ×3, HN newest |
| **P2**（每 6-24h, 7200-21600s） | 低频 | arXiv, GitHub Blog, Krebs, OilPrice, Fed/ECB press, Le Monde(fr), DW 中文, B站热门, Vimeo, euronews/France24 |

规则: 同域每轮 ≤2 请求；条件 GET（ETag/If-Modified-Since）；404/500/429 退避（YouTube 间歇故障 ×3 重试；GDELT/Reddit 429 当轮放弃+冷却）。

## 2. 各层实测要点（✅=本次 200 实测）

### 2.1 官方 RSS（主力）
✅ BBC(5 分区)/Guardian(5 分区)/AJ all/DW(rdf-en-all 134 条, 0.1h 新鲜)/NYT World/CNBC(4 个, `/id/{id}/device/rss/rss.html` 格式)/MarketWatch/Yahoo Finance/OilPrice/Fed/ECB press/ReliefWeb/UN News/ToI/SCMP/France24/Euronews/Le Monde/THN/Krebs/Ars/Verge/TechCrunch/Wired/Engadget/GitHub Blog。
❌ **已确认死亡/不可用**: Reuters 官方 RSS(404+robots 全禁)、AP(401 "Invalid client credentials")、CNN rss(TLS 断连)、Bloomberg(付费墙无 feed)、NHK(形式 200 实质停更 757h)、BleepingComputer(CF 403)、hnrss.org(502×3 不稳定)。
→ 替代: **GNews `site:` 限定**（reuters 实测 100 条/24h）+ Bing News RSS + THN/Krebs 补安全位。

### 2.2 发现渠道（元层）
✅ GNews topic/search（hl/gl/ceid 参数齐备, 中文版 200）；✅ Bing News RSS（`qft=sortbydate` 排序, link 需解包 `url=` 参数——collector 已实现 `_unwrap_bing`）。
⚠️ GNews robots 未放行 /rss/（灰区）: 低频、自报 UA、只存元数据+正文提取、不二次分发全文。

### 2.3 News Sitemap（全量新文章发现, 隐藏金矿）
✅ Guardian `sitemaps/news.xml`（460 条/分钟级, 带 news:title）；✅ NYT `sitemaps/new/news.xml.gz`（607 条, 实际未压缩, robots 明文禁 TDM——只存标题+URL 元数据）；✅ BBC index `sitemaps/https-index-com-news.xml`（→子 sitemap 链式, collector 已实现）。
**经验: sitemap 真路径只能从各站 robots.txt 的 `Sitemap:` 行取, 猜路径必 404/403。**

### 2.4 API（JSON 适配器）
✅ HN Algolia（front_page + search_by_date, JSON）；✅ Bilibili `web-interface/popular`（免登录, 元数据齐）；❌ bilibili wbi 空间 API 需签名(-403)。
预留: GDELT lastupdate.txt 200（events/gkg 15min CSV 批次——Phase 6+ 可选, doc API 本 IP 全 429）。

### 2.5 视频/流媒体（只存元数据红线）
✅ YouTube 频道 feed（BBC=`UC16niRr50-MSBwiO3YDb3RA`, AJ=`UCNye-wNBqNL5ZzHSJj3l8Bg`, DW=`UCknLrEdhRCp1aegoMqRaCZg`——均从 @handle 页 externalId 核实; **自带 media:starRating + media:statistics views 热度指标**; 间歇 404/500 必须退避重试）。
⚠️ YouTube robots `Disallow: /feeds/videos.xml`（灰区: 低频 1h、只存 videoId/标题/频道/时间/缩略图 URL/views、不落地媒体流）。
✅ Vimeo staffpicks RSS、PeerTube(framatube feeds+search API)；❌ Rumble(无 RSS)、Twitch(helix 401 需 key)、RSSHub 公共实例(403/503, 官方声明仅测试)。
B站: ✅ 官方 popular API（RSSHub 路线放弃）。

### 2.6 事件/社会层
✅ ReliefWeb RSS（灾害/人道）；✅ Wikipedia Current Events Portal（当日页 + api.php parse JSON 可结构化——Phase 4+ 可选 handler）；❌ ISW feed 403（post-sitemap6.xml 200 可用但常规 sitemap 无标题, 暂缓）；❌ ACLED(需 key)、Wikinews(停滞)。

## 3. 合规红线（写入采集器行为的硬约束）

1. 描述性 UA（NewsResearchBot/0.1）+ 每域 ≥1.2s 间隔 + 条件 GET + 并发 1
2. **绝不绕过**: CAPTCHA/登录墙/付费墙/访问控制/Cloudflare 挑战
3. 403/429 → 退避+冷却+计数，5 连败自动停用（不硬爬）
4. 付费墙媒体（FT/Bloomberg/NYT 部分）只取 RSS 标题+摘要（meta_only 语义）
5. 视频: 只存元数据（videoId/标题/频道/时间/缩略图 URL 热链/views/starRating/描述≤200 字）——不下载媒体流/字幕/完整描述
6. robots.txt Disallow 的 feed 端点（YouTube/Reddit/GNews）= 灰区策略: 极低频+元数据+不二次分发；BBC News Sitemap 等按 robots 放行范围使用
7. GDELT 署名、ReliefWeb appname 署名、Wikipedia CC BY-SA（展示层注明来源）

## 4. 降级矩阵（源失效时）

| 失效源 | 降级路径 |
|---|---|
| Reuters RSS(死) | GNews site:reuters.com ✅ |
| AP(401) / CNN(TLS) / Bloomberg(墙) | GNews site: / Bing News / CNBC+Yahoo+MarketWatch |
| NHK(停更) | GNews site:nhk.or.jp（未部署, 备选） |
| BleepingComputer(CF 403) | THN + Krebs ✅ |
| hnrss.org(502) | HN Algolia API ✅ |
| rsshub.app(403)/rssforever(503) | B站官方 API ✅（其余 RSSHub 路线一律绕开） |
| GDELT doc API(429) | lastupdate.txt events CSV（Phase 6+）或弃用 |
| Reddit 429 | 降频 6h + 仅元数据；或 GNews site:reddit.com |
| 任意源 5 连败 | 自动 disabled（seed 重置可恢复） |

## 5. 扩展指南（新增源）

1. 用 `SOURCE_PROBE_results.tsv` 同款方法实测端点（状态码+形态）
2. 读 robots.txt（feed/sitemap 放行范围）
3. 加进 sources.seed.json（slug/kind/feed_url/category/language/priority/poll_seconds）
4. `newsctl seed-sources` → 自动进入分片轮询；5 连败自动停用即"实测失败"
5. 新平台类型 → collector._ADAPTERS 加适配器（JSON API），或 kind=sitemap/gnews 复用
