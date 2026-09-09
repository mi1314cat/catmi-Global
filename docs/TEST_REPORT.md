# TEST_REPORT — 验收测试报告（Phase 0-8 全量）

> 测试时间: 2026-09-09 · 环境: s12.serv00.com 生产（非模拟）· 出口: 本地→HK 数据中心
> 原则: 所有数字来自真实 HTTP/SSH 执行记录; AI 全程零参与（零 API 调用, 系统 AI-free 验证成立）

## 1. 采集管道（Phase 1-3）

| 项 | 结果 | 证据 |
|---|---|---|
| 49 源注册 | ✅ inserted 21 + updated 28 = 49, 0 错误 | seed-sources JSON 输出 |
| 多类型扫描 | ✅ rss/gnews/sitemap/api 全通: 583 新/445 重/6 错, 20s | p3full.out |
| 正文提取 | ✅ 25/25 done (trafilatura), 30s; 29+1/30 done 第二批 | fetch JSON |
| 图片下载 | ✅ 12/12 (HEAD 预检+≥3KB), og 图 62KB 落盘 | images JSON + /api/images/1 200 |
| 去重 | ✅ canonical_url + content_hash 双通道; 同源标题 Jaccard≥0.9/48h | dupe 计数 36/445 |
| 事件聚类 v2 | ✅ 每批 300 篇归并 52→74→**119**（跨源锚点: Canada×5 检索命中; e:canada/e:trump 指纹可见） | stories_fts MATCH |
| Trending | ✅ 429 事件重算; top: PISA(3源3篇)/俄朝大桥(3源) heat 1.92/1.24 | trending JSON |
| 视频元数据 | ✅ YouTube×3 + B站热门 meta_only 入库（不落地媒体流） | per-source items |
| 断点队列 | ✅ 1097 pending 任务状态机; 失败 0; 退避 1h/4h/12h | crawl_tasks |

## 2. 服务层（Phase 4-5）

| 端点 | 实测 |
|---|---|
| GET /api/health | 200 {articles:1163, stories:248, sources:52, disk:normal} |
| GET /api/news?q=tariff | 200 FTS+snippet; /api/news/latest 分页 {total,limit,offset} |
| GET /api/news/35 | 200 全文+作者(Maya Yang)+canonical |
| GET /api/stories?q=Canada | 200 total=5（聚类生效）; /api/stories/:id timeline[] |
| GET /api/trending | 200 heat 排序 |
| GET /api/sources /categories | 200 52 源 / 类别计数 |
| GET /api/images/1 | 200 image/jpeg 62191B（路径遍历防护已做） |
| 未知端点 | 404 JSON + hint |
| MCP initialize | 200 protocolVersion 2025-06-18, serverInfo 正确 |
| MCP tools/list | 200 8 工具全 schema |
| MCP tools/call get_trending / search_news | 200 真实数据（PISA 1.924 / tariff 检索） |
| MCP 错误 token / 无认证 | 401 ×(10/10) + WWW-Authenticate |
| Origin 伪造 | 403 origin rejected |

## 3. 压力测试（Phase 8, 生产环境实测）

**python3 tests/stress_api.py**（浏览器 UA——Python 默认 UA 被 serv00 前端 WAF 拦 403, 已记录为平台行为）:

| 场景 | n | 结果 |
|---|---|---|
| 顺序基线 10× | 10 | 10× 200, p50 116ms, max 312ms（含 Passenger 冷启动 5.4s → 重生实测） |
| **正常负载 90×并发5** | 90 | **90× 200, p50 416ms, p95 1031ms, max 1526ms, 0 错误** |
| **突发 150×并发20** | 150 | 20× 200 + **130× 429**（限速器 120/min 精准生效） |
| MCP tools/call 40×并发5 | 40 | **40× 200, p50 411ms, max 483ms, 0 错误** |
| MCP 无认证 10× | 10 | 10× 401 |

## 4. 韧性/自动化（Phase 7-8）

| 项 | 结果 | 证据 |
|---|---|---|
| Passenger kill→重生 | ✅ kill 后首请求 200 | ssh kill + curl |
| cron 自动触发 | ✅ 06:10 槽位执行（首跑暴露 run 参数 bug→已修复→手动 run 全链成功 33s） | cron.log + manual-run.out |
| 管道单轮耗时 | ✅ 33s（scan 10 源+fetch 12+images 8+cluster 300+trending 429） | run JSON |
| lockf 防重 | ✅ /tmp/news-run.lock | crontab |
| 备份 | ✅ 机制就绪（04:10 每日, 保留 7 份） | backup API 实现于 newsctl |
| 磁盘水位 | ✅ normal 130M/3G（4.3%）; 四档门已实现 | monitor_level |
| 72h 滚动 | ✅ purge_content/images/raw 已实现并在 cleanup 链 | retention.py |
| doctor | ✅ quick_check/FTS 漂移/卡死任务/WAL 检查 | newsctl doctor |

## 5. AI-free 验证
全链（采集→提取→聚类→检索→API→MCP→UI）在**零 LLM API 调用**下完成与验收——AI Provider 仅是 env.local 可选插件（未配置时系统满功能）。

## 6. 已知边界（诚实记录）
1. 聚类扫描 300/轮: 1162 篇积压需数轮追平（cron 10min 节奏 4 轮内完成）; 同窗跨源合并依赖锚点共现
2. GDELT doc API 对数据中心 IP 429×5（已记录, Phase 6+ 可选 lastupdate 路线）
3. ecb/arxiv/vimeo 3 源 0-item 系 limit 49 截断（非故障, 下一轮次自然进入）
4. Python-urllib UA 被 serv00 前端 WAF 403——API 客户端需自设浏览器 UA（记录于部署手册）
5. 深夜抓取积压批次 fetch 25/轮 → 大新流量时追平需 ~7h（可调 FETCH_BATCH）
