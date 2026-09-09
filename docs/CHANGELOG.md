
# 2026-09-09 Phase 2-5 冲刺（同一工作日）

## Phase 2 正文/图片提取 ✅
- extractor.py: 抓取→trafilatura(JSON favor_recall)→Scrapling 兜底→rss_summary 兜底; canonical 识别; content_hash+canonical_url 双重去重; FTS5 写入（**修复: FTS5 虚拟表不支持 UPSERT → DELETE+INSERT, 且先写 FTS 再改 articles 防半态**）
- images.py: og/twitter/srcset 候选评分 + HEAD 预检(≤8MB) + ≥3KB 校验 + 磁盘水位门
- 实测: 25 篇 30s 全提取 0 失败; 图片 10/10

## Phase 3 聚类/Trending ✅
- collector.py v2: handler 注册表（rss/gnews/sitemap/api）—— gnews 尾缀剥离+发布者域名、news sitemap（gzip 探测+sitemapindex 链≤3）、API 适配器（hn_algolia/bilibili_popular）、视频元数据直插（meta_only）; Bing RSS 链接解包
- stories.py v2: 专名锚点 containment≥0.5 + 标题 Jaccard≥0.30 双通道; 源类别门（general 源不设门）; stories_fts 同步填充; 指纹 v1/v2 兼容
- 实测: 49 源 1163 篇; 52-74/300 归并/批次; 事件检索命中（Canada×5, West Bank 家族待多轮聚类追平——300/轮扫描上限, cron 连续轮次覆盖）
- trending.py: heat=Σ 源优先级×时间衰减, 248 事件重算

## Phase 4 REST API ✅（上线）
- web/app.js + web/lib/newsdb.js: 零框架 Node 22, node:sqlite 只读, 10 端点, 限速 120/min, 请求日志脱敏, 5MB 轮转
- 部署: public_nodejs/app.js 替换（占位 v0 已备份 ~/backup/app.js.v0.bak）——**修复: 旧 Passenger 进程残留需 kill 重生**
- 实测: 10 端点全 200; 图片流 200/62KB; JSON 404; 域名根页不受影响

## Phase 5 MCP ✅（上线）
- SDK @modelcontextprotocol/sdk 1.30.0（node_modules 2.0M, npm 秒装）
- StreamableHTTPServerTransport: **无状态（sessionIdGenerator:undefined）+ enableJsonResponse:true**（2025-06-18 现役协议; 2026-07-28 规范双时代路线见 MCP.md/MCP_CHECK_FULL.md）
- 8 只读工具: search_news/search_events/get_event/get_article/get_trending/search_media/get_timeline/list_sources
- 安全: Bearer 必需(env.local 600, 不落日志) / Origin 白名单 / Host 校验 / 256KB 上限 / 60 req/min / 401+WWW-Authenticate
- 实测: initialize(2025-06-18)/tools/list(8)/tools/call get_trending(真实数据)/错误 token 401/无认证 401

## 生产 cron ✅
*/10 run(lockf 防重) · 35* cleanup · 10 4* * * backup · 20 4* * * doctor

## 研究整合
- MCP 规范研究（MCP_CHECK_FULL.md, ~500 行）: 最新 2026-07-28 破坏性变更; 双时代单端点策略
- GitHub 增量核查（GITHUB_CHECK_FULL.md）: MuckScraper MIT 坐实+活跃; Pharos 专有; Heatwire 弃置; FreshRSS AGPL 借实践; 新增 newsnow/feedgrab/defuddle/feed-mcp/Trends-MCP 六项目

# 2026-09-09 生产验收审计（下午轮次）

## 审计发现并修复（全部有回归证据）
1. **调度饥饿**: due 排序改按逾期比率（P0 不再饿死 P2）→ B站 20 条 / YouTube 15+15 条首次入库
2. **视频被类别门排除聚类** → video 跳过门 → 23/60 视频进入多源 Story（West Bank 事件含 YT BBC ×5）
3. **LIKE 兜底失效**（q=OpenAI 返回 847 全量）→ 精准 1 条
4. **单锚点误聚**（匈牙利簇混入 Engadget×3）→ 最小交集≥2 规则 → 全量重建 5 轮收敛
5. limit=-5 绕过分页 → Math.max(1,...) 钳制
6. cleanup 可观测性（last_cleanup meta）+ WAL checkpoint(TRUNCATE)（4.2MB→0 实证）
7. 图片失败: 标记行保 URL + crawl_errors 落日志（image ×10 已见）
8. /api/news/search 与 /api/stories/search 显式别名; /api/status 组件级磁盘（db/wal/images/cache/pct）
9. YouTube 源降频 6h（间歇 404×重试; serv00 端实测可用）

## 审计交付
CURRENT_STATUS.md（20 问全答, 现场取证）/ SOURCE_INVENTORY.md（52 源盘点+地域语言差距表）/ PRODUCTION_AUDIT.md（已完成/部分/bug/风险/优化 分级, 11 bug 全修复记录, MCP Agent 6 场景模拟实录）

# 2026-09-09 Global Intelligence 升级（下午第二轮）
## 新能力
- Web Search provider 层（5 keyless + SearXNG PRIMARY 插槽, 零 API Key, 降级可观测）
- URL Reader（复用管道提取栈的 Python 子进程, 并发≤2, 状态语义 ok/inaccessible/needs_js/failed）
- Unified Query Service（REST/MCP/UI 共享; scope=web|intelligence|all）
- deep_search 多步研究编排（无 AI, 40s 预算）
- MCP 8→12 工具; REST +/api/search /api/media; /api/status 增 MCP 真实状态
- Web UI 重定位: Intelligence Console 六视图（真实数据, 零假状态）
## 修复
- MCP async 工具 "{}" bug（await）; provider 错误分支名; deep_search 返回结构; reader Fetcher 签名
