# SOURCE_INVENTORY — 当前源注册表实测盘点（52 源, 全部 kind/类别/语言）

> 数据源: `sources` 表直查（2026-09-09）。质量依据: SOURCE_PROBE_FULL.md（~170 实测请求）+ 6h 实产数据。

## 1. 按采集类型统计

| 类型 | 数量 | 说明 |
|---|---|---|
| RSS/Atom（feedparser 统一处理） | 41 | 主力; 含 YouTube 频道 RSS ×3（元数据红线）、Vimeo ×1 |
| News Sitemap | 3 | Guardian/NYT/BBC（标题级、分钟级、robots 路径实测） |
| API（JSON 适配器） | 3 | HN Algolia ×2（front+newest）、Bilibili popular |
| Google News（gnews handler） | 4 | WORLD / BUSINESS / 中文版 / site:reuters.com |
| RSSHub | 0 | **主动弃用**（公共实例 403/503 不稳, 官方声明仅测试） |
| Crawl4AI | 0 | 主机不可行（已证）; 设计为外部渲染 fallback, 默认关 |
| Scrapling | 0 直采 | 仅作正文提取兜底层（本批数据 trafilatura 138 篇, 兜底尚未触发——主链成功率足够高） |
| 普通网页直爬 | 0 | 不做（合规 + 带宽）; 文章正文一律通过 feed→文章页提取 |

## 2. 按主题分类（源数）

| 主题 | 数量 | 明细 |
|---|---|---|
| 新闻/综合 | 11 | gnews-world/zh, BBC world, Guardian world, AJ, DW-en/zh, NYT world, France24, Euronews, Le Monde(fr), +3 家 sitemap |
| 科技 | 16 | HN×2, Ars, Verge, TechCrunch, Wired, Engadget, THN, Krebs, arXiv, GitHub Blog, BBC tech, Guardian tech + (遗留 hnrss/bleeping/npr) |
| 财经 | 12 | CNBC×4, MarketWatch, Yahoo Finance, OilPrice, Fed, ECB, gnews-business, BBC business, + sitemap 部分 |
| 政治/国际/地缘 | 8 | gnews-reuters（Reuters 替代）, Guardian world, AJ, ToI, SCMP, UN News, ReliefWeb, reddit-worldnews |
| 社会 | 1 | ReliefWeb（灾害/人道; 部分 soci­ety 关键词启发式归入 general 文章） |
| 视频 | 5 | YouTube AJ/BBC/DW, B站热门, Vimeo |

## 3. 地域覆盖审计（诚实差距表）

| 区域 | 覆盖 | 判定 |
|---|---|---|
| 美国 | 强（AP/CNN 官源死, 但 NYT/CNBC/Yahoo/GNews 补位） | ✅ |
| 中国 | 中（B站热门 + gnews-zh + DW 中文; 缺大陆主流英文出口如 Xinhua/GlobalTimes） | ⚠️ |
| 欧洲 | 强（Guardian/BBC/DW/France24/Euronews/LeMonde/ECB） | ✅ |
| 俄罗斯/乌克兰 | **弱**: 仅经由 BBC/Guardian/NYT 二手报道; 无俄乌直源（RT/TASS probe 为 P2 可行, Interfax-Ukraine 未实测） | ❌ 缺口 |
| 中东 | 中（AJ EN + ToI; 缺 AJ 阿语版 / Al-Monitor） | ⚠️ |
| 日本 | **0 直源**（NHK EN feed 实测停更 757h; NHK Web 源需另行实测 `www3.nhk.or.jp/rss/`） | ❌ 缺口 |
| 韩国 | **0**（Yonhap RSS 未实测） | ❌ 缺口 |
| 东南亚 | **0**（CNA/Channel NewsAsia 未实测） | ❌ 缺口 |
| 印度 | **0**（The Hindu/NDTV/TOI India 未实测） | ❌ 缺口 |
| 拉美 | **0**（Mercopress/Buenos Aires Times 未实测; Le Monde/部分 gnews 间接） | ❌ 缺口 |
| 非洲 | **0**（AllAfrica RSS 未实测; UN News/ReliefWeb 部分覆盖非洲事件） | ❌ 缺口 |
| 澳洲 | **0 直源**（ABC.net.au RSS 未实测） | ❌ 缺口 |

## 4. 语言覆盖审计

| 语言 | 源数 | 占比 |
|---|---|---|
| 英文 | 46 | 88% |
| 中文 | 3 | 6% |
| 法文 | 1 | 2% |
| 日/韩/俄/阿拉伯/西/德 | **0** | 0% |

**明显偏科**: 英文 88%。缓解因素: gnews WORLD/BUSINESS 聚合全球媒体（含部分当地语言媒体的英译标题）; 但原生视角（日/韩/俄/阿语）缺失是事实。
**合规纪律**: 补源必须走同一流程——先 robots.txt + 端点实测（同 SOURCE_PROBE 方法）, 再入 seed; 不盲配。

## 5. 质量与重复度审计

- **重复度**: 跨源同一事件靠聚类合并（1 事件 9-14 源属正常）; 真正的冗余源: `hn-frontpage`（hnrss.org, 30 条/轮且与 hn-algolia 高度重叠, **建议退役**——Algolia 更稳）; `npr-world`/`bleepingcomputer` 为早期遗留, 产量低但无害。
- **单源产量 6h 实测**: gnews-business 64 / yahoo 63 / nyt-sitemap 60 / gnews-world 56 / gnews-zh 51 —— P0/P1 分层轮询工作正常。
- **死源/封锁现状**: YouTube 3 频道间歇 404（serv00 端实测可通 ×2/3, 重试机制覆盖; 我方本地出口被端级 404）; Reuters/AP/CNN/Bloomberg 官源已死（用 gnews site: 替代——见 SOURCE_STRATEGY.md §4 降级矩阵）。
- **视频 vs 新闻关联**: 实测 60 视频中 23 篇已进多源 Story（例: West Bank 事件含 YouTube BBC News ×5 + 8 家媒体）——修复类别门后已生效。

## 6. 扩展建议（下一步补口, 全部先实测）

优先级: 日本 NHK web rss > 韩国 Yonhap > 东南亚 CNA > 印度 The Hindu > 俄 Interfax-Ukraine/TASS > 阿 Al Jazeera Arabic > 西 El País > 德 DW-de（端点已实测 200, 直接加）> 澳 ABC > 拉美 Mercopress > 非洲 AllAfrica。
预计 +11 源后语言分布: en 78%, zh 5%, fr 2%, ja/ko/ru/ar/es/de 13% —— 偏科显著改善。

---

# 2026-09-09 地域扩容（+12 源 → 64 源）

用户优先级: 中国大陆/台湾/香港 > 日韩 > 印俄。全部经服务器实测（HTTP 200 + 真实条目）后入册:

| 源 | slug | 语言/地区 | 探测结果 |
|---|---|---|---|
| 中国新闻网 | cn-chinanews | zh/CN | 30 条 ✓ |
| GNews 中国大陆 | cn-gnews-china | zh/CN | ✓（gnews 适配器） |
| GNews 台湾 | tw-gnews | zh-Hant/TW | ✓ |
| 南华早报 SCMP | hk-scmp | zh/HK | 50 条 ✓（跟随跳转） |
| 香港电台 RTHK | hk-rthk | zh/HK | 19 条 ✓ |
| NHK | jp-nhk | ja/JP | 7 条 ✓ |
| 朝日新聞 | jp-asahi | ja/JP | 41 条 ✓ |
| 韩联社(英文) | kr-yonhap | ko/KR | 102 条 ✓ |
| The Hindu | in-thehindu | en/IN | ✓ |
| Times of India | in-toi | en/IN | ✓ |
| 塔斯社 TASS | ru-tass | en/RU | 100 条 ✓ |
| RT | ru-rt | en/RU | 100 条 ✓ |

探测失败淘汰: ChinaDaily(404)、RT中文(401)、自由时报/中央社(404, URL 已失效)、YahooJP(403 bot)、Yonhap韩文(404)、Kommersant(RU 602 条, 暂缓可后补)。
