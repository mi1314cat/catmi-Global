# PRODUCTION_AUDIT — 生产验收审计报告（2026-09-09）

> 方法: 现场取证（audit1-4.sh + web.log + SQLite 直查）+ 真实 MCP Agent 模拟 + API 合同逐端点实测。
> 原则: 不隐瞒问题; 每项标注实测证据。**结论: 架构方向正确, 无需破坏性重写**（未出具 ARCHITECTURE_REVIEW.md, 因未发现方向性错误——双进程 + 单 SQLite WAL + 只读服务层的结构在全部压力与故障注入下成立）。

## 1. 已完成（有生产证据）

| 项 | 证据 |
|---|---|
| 采集管道 49 源 4 类型（rss/sitemap/api/gnews）自动运行 | cron 3 槽位自动成功（06:10/20/30）; 24h 1308 篇 |
| 正文提取（trafilatura 主链 + Scrapling 兜底 + rss_summary 兜底） | extract_method 分布: trafilatura 138 / meta_only 50 / rss_summary 1 |
| 双重去重（canonical + content_hash + 同源标题 Jaccard） | dupe 38（canonical 命中）+ fetch 轮内 dupe 14/轮 |
| **事件聚类 Article→Story 跨源归并** | Story #167/170 West Bank: **16-21 篇 × 8-14 独立源**（YouTube BBC 视频 + Reddit + NYT/Guardian/DW/CNBC/NPR/ToI/Euronews/France24/sitemap）; 算法 = 专名锚点 containment≥0.5 **且交集≥2** 或标题 Jaccard≥0.30, ±72h 窗, 类别门——**不是简单关键词匹配**（v2 修复单锚点误聚后实证: 匈牙利簇不再含 Engadget/HN 噪声成员） |
| Trending heat（独立源×时间衰减） | heat 7.1（16篇/11源）; 24h 窗重算 696 事件 |
| REST API 11 端点 | 逐端点实测全 200（含 /api/news/search、/api/stories/search 别名、/api/status 组件级磁盘）; limit 负数边界已修; 限速 120/min 实证（429×262） |
| **MCP Server（Streamable HTTP, 认证, 只读）** | 真实客户端模拟 6 场景全过（见 §6）; Bearer 必需（无认证 10/10 → 401）; Origin/Host 校验; 256KB body 上限 |
| Web UI（信息架构合规） | 搜索框+最新/热点/事件/视频/源/状态, 60s 刷新, 无门户化 |
| 72h 滚动 + 磁盘 4 档保护 | cleanup 实跑（content_purged 1, last_cleanup meta 落盘）; WAL checkpoint 实证 4.2MB→0; 图片失败标记行防重试风暴 |
| 备份/体检/恢复命令 | newsctl backup（SQLite backup API, 保 7 份）/ doctor（quick_check+FTS 漂移实测 OK）/ restore |
| **AI 全程零依赖** | 全部验收在零 LLM 调用下完成; AI 仅 env.local 可选 Provider |
| 秘密零泄漏 | MCP_TOKEN 仅 env.local(600); 文档 26 份无任何真实凭证; web.log 脱敏（无 Authorization/query/body） |

## 2. 部分完成（能用但有已知缺口）

| 项 | 现状 | 缺口 |
|---|---|---|
| 视频元数据 | 60 篇（platform 隐含于源 slug; 标题/频道/时间/缩略图/描述≤200 字/YT views） | **无 transcript/captions**（robots 灰区+成本, 未采）; B站无 views 字段映射; 无独立 `platform` 列（建议加） |
| 视频↔新闻事件关联 | **23/60 视频已进多源 Story**（修复类别门后实证）; YouTube BBC×5 进 West Bank 事件 | YouTube/B站新视频依赖下轮 cluster 追平; gnews-reuters 在簇中参与度未逐簇核验 |
| 磁盘监控 | du 水位 4 档（管道联动降级）+ /api/status 组件级（db/wal/images/cache/文件数/pct） | **inode 监控**只报文件数, 未设阈值联动; 组件级未入 cron 告警（无邮件/webhook 通道——serv00 无出站通知, 建议用 trending/状态页承担） |
| 地域/语言覆盖 | 46 en / 3 zh / 1 fr | 日/韩/俄/阿/西/德/印/东南亚/拉美/非洲/澳 **0 直源**（SOURCE_INVENTORY §3 全表 + 补源清单） |
| 积压队列 | pending 1119（done 139）, bounded（fetch 30/轮 vs 新增 ~40/轮, 长尾稳态） | 长尾文章正文提取延迟数小时（元数据即时可用, 不影响检索/聚类） |

## 3. 只是 UI 有入口但后端尚未完成

**无。** 六个视图全部走真实 /api 查询; /api/status 为真组件数据。（UI 的"源"页含 disabled 标记与连败数, 后端字段真实。）

## 4. 存在 Bug（本审计发现 → 全部已修复, 附验证）

| Bug | 根因 | 修复+验证 |
|---|---|---|
| 调度饥饿: P0 源每轮占满 16 槽, YouTube/B站从未被扫 | due 排序按 priority | 改按逾期比率降序 → B站 20 条/YT 15+15 条首轮即入 |
| **视频无法聚入新闻事件** | 类别门把 video 当独立类 | video/general 一样跳过门 → **23 篇视频进多源事件** |
| LIKE 兜底失效（q=OpenAI 返回 847 全量） | fallback 未接收 like 参数 | 修复 → q=OpenAI 精准 1 条 |
| 单锚点误聚（匈牙利簇混入 Engadget×3/HN） | containment 对单泛锚点=1.0 | **最小交集 ≥2 规则** → 全量重建 5 轮收敛, 垃圾成员消失 |
| limit=-5 绕过分页（SQLite 负 LIMIT=无限制） | 未钳负值 | Math.max(1,...) → 返回 1 行 |
| cleanup 不可观测 + WAL 膨胀 | 无 meta/checkpoint | last_cleanup 落盘 + wal_checkpoint(TRUNCATE)（实测 4.2MB→0） |
| 图片失败既丢 URL 又无日志 | 失败即置 NULL | 标记行保留 URL + crawl_errors 落日志（image/image ×10 已见） |
| seed() 丢 adapter 列 → API 源全败 | INSERT 缺列 | 已补（HN/B站适配器工作） |
| cron run 参数 bug（scan_limit AttributeError） | 首槽暴露 | 修复 → 连续 3 槽自动成功 |
| FTS5 无 UPSERT（历史） | 虚拟表限制 | DELETE+INSERT + 先 FTS 后 articles |
| 旧 Passenger 进程挡新代码 | kill 前未重生 | 备份→kill→按需重生（实测 3 次） |

## 5. 资源风险

| 风险 | 评估 | 缓解 |
|---|---|---|
| 磁盘 | 139MB/3GB = 4.6%（安全）; 稳态 <250MB | 4 档自动降级已实现 |
| WAL 膨胀 | 曾 4.2MB; checkpoint 后 0 | cleanup 每轮 checkpoint; 若读连接持有锁会 PASSIVE（尺寸有界, doctor 监控 wal 字节数） |
| inode | 9,711 文件（大头是 venv/node_modules 静态开销） | 图片/缓存 72h 自动清; 无失控目录 |
| CPU/内存 | Passenger 单实例 idle 0.0%; 管道轮次 45s/10min（<8% 占空比） | 无常驻重进程 |
| HN 重复 | hn-frontpage（hnrss）30 条/轮与 Algolia 高度重叠 | **建议退役 hn-frontpage**（保留 Algolia 双通道） |

## 6. 安全风险（按风险排序, 全部为设计决策而非事故）

1. **REST API 公开读**: 无认证（限速 120/min + 只读）。决策: 公开读是产品语义（浏览器/脚本友好）; 敏感操作全在 MCP 侧。若需收紧: 加 IP 白名单或 Bearer（30 行改动）。
2. **MCP 已认证**（Bearer/401×13 实证/Origin/Host/256KB/60 min⁻¹）——达标。
3. 无自动封禁/告警通道: 持续滥用只产生 429（有日志）; 建议后续加 web.log 异常告警（低优先级）。
4. 依赖供应链: 仅官方 SDK + 94 包; 锁定版本手动升级。

## 7. 推荐优化（按收益/成本排序）

1. **补 11 个地域直源**（SOURCE_INVENTORY §6 清单, 每源 10 分钟实测流程）→ 全球覆盖从"经由英媒二手"到原生
2. **退役 hn-frontpage**（hnrss 冗余）
3. articles 加 `platform` 列 + B站 views 映射（视频元数据完整性）
4. /api/sources 分页（当前 16KB 全量返回; 源数 100+ 时需要）
5. gnews 重定向 fetch 成功率量化（当前 fetch 30/轮含 gnews 链接, trafilatura 成功率高; 建议统计 extract_method 按 source 分组, 一条 SQL 的事）
6. 72h 复验（系统运行满 72h 后重跑 audit1: 验证 purge 量、图片清理、DB 尺寸平稳）
7. videos 中 transcript 字段预留 schema（不采集, 列先建）

## 8. Agent 模拟测试记录（MCP, 真实数据非 Mock）

| # | 请求 | 工具 | 结果（实测） |
|---|---|---|---|
| 1 | "过去 24h 全球重大事件" | search_events{hours:24} | AfD 选举(8p/2s)、挪威国王加冕(4p/3s)、**Bombardier(15p/9s)、West Bank 制裁(21p/14源)**、法国博物馆失窃(5p/5s) |
| 2 | "最近 24h 关于 OpenAI 的新闻" | search_news{q:OpenAI} | **修复后: 精准 1 条**（"AI will cure cancer…UK chip boss" BBC——正文含 OpenAI）; 修复前 847 全量（bug） |
| 3 | "热度最高的事件" | get_trending | heat 7.109 匈牙利(16p/11源)、6.869 美海军六代机(9p/7源)、6.622 West Bank(21p/14源) |
| 4 | "某 Story 的所有来源" | get_event{id} | 匈牙利簇 11 源构成（DW×2/Euronews×2/BBC×2/Guardian…, 修复后无科技噪声） |
| 5 | "某事件 72h 时间线" | get_timeline{id} | 16 条按时间升序（09-06 DW → 09-08 BBC/Euronews/Reddit/Guardian…） |
| 6 | "搜索最近的视频热点" | search_media{hours:72} | 50 条（YT AJ 3 条 + B站热门 2 条; story_id 归并依赖下轮 cluster——已验证 23 条带 story） |

链路全程: Agent 请求 → JSON-RPC tools/call → 同一 SQLite(WAL) → 真实文章/事件行 → JSON 返回（延迟 66-414ms/调用）。

## 9. 结论

**系统达到"第一版生产可用"标准**: 采集→提取→去重→跨源事件聚类→检索→REST→MCP→UI 全链在真实数据与真实客户端下工作; 72h 滚动/磁盘保护/cron/备份/恢复全部落地。审计发现 11 个 bug 全部修复并有回归证据; 无架构方向错误; 主要差距是**地域直源覆盖**（有清单、有纪律、可按需补）与视频元数据字段完整性（小改动）。域名与 SSL 未做任何变更, 密码/Token 零入文档。

---

# v2 增补审计（2026-09-09 Global Intelligence 升级后）

## 新能力验收（全部生产实测）
| 能力 | 验收证据 |
|---|---|
| Web Search（互联网, 零 key） | 服务器端实测: "Nvidia earnings"(news/week) → gnews+bingnews ok 真实结果; 中文查询 → gnews 中文媒体命中; provider 间歇封禁自动降级（ddg/bing error 时整体仍成功）; providers[] 状态/延迟记录; scope=web|intelligence|all 三态实测（web 3 结果 / intel 12 / all 双通道） |
| URL Reader | Guardian 文章 3978 字符/2.0s（trafilatura）; bbc.com/news 6921 字符; 状态语义 ok/inaccessible/needs_js; 不绕过访问控制（401/403/429 → inaccessible）; 子进程并发≤2 |
| deep_search | "UK West Bank sanctions" → web 选源 → 读页 1468 字符 → 情报库 9 篇/58 事件关联, 2.3s（无 AI, 40s 预算） |
| MCP 12 工具 | tools/list 12 全 schema; async 工具 "{}" bug 修复后全部返回真实数据; 错 token 401 |
| Web Console | 六视图（Overview/Search/Events/Sources/Media/System）; Search 三 scope 带 WEB/INTELLIGENCE 标签; Sources 可筛选; System 全真实状态（MCP enabled:true 12 tools 来自运行时）; 移动端断点+表格横向滚动 |
| REST | 14 端点全 200（+ /api/search /api/media）; limit 负值钳制 |

## 资源影响（实测）
进程 3（node+curl 计数内）/20 · 磁盘 146MB/3GB（4.9%）· 文件 9,798 · **零新增依赖/零新增常驻进程**（websearch 在 Node 进程内; reader 是短命子进程≤2）

## v2 遗留
- SearXNG PRIMARY 未配置（等待用户提供 VPS/实例 URL; 未配置时 5 个 keyless provider 正常工作）
- ddg/bing HTML 对数据中心 IP 间歇 bot 拦截（降级已覆盖; 新闻类查询 gnews/bingnews 最稳）
- read_url 对重度 JS 页返回 needs_js（Crawl4AI 默认关——如需可后续加外部渲染钩子）
