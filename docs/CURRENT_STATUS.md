# CURRENT_STATUS — 真实运行状态盘点（2026-09-09 审计, 全部来自现场取证）

> 方法: SSH 现场检查 + 直查 SQLite + 实际 HTTP 请求, 不依据任何文档/代码推断。
> 证据脚本: 服务器 `~/news-lab/audit1-4.sh`, 结果在 `~/news-lab/results/*.out`

## 一~四、运行环境（问题 1-4）

| 项 | 实测 |
|---|---|
| 1. 运行程序 | **双进程**: ① 采集管道 `newsctl run`（Python, cron 每 10min, lockf 防重）② Web 服务 `app.js`（Node, Passenger 按需常驻） |
| 2. 语言 | 两者都用: 管道 **Python 3.11.13**（venv, trafilatura/feedparser/httpx）; 服务层 **Node v22.22.2**（node:sqlite 只读） |
| 3. Web Server | **Passenger + nginx**（serv00 托管）: `public_nodejs/app.js` 236 行零框架; 进程实测 `node22 idle <你的域名> (production)` |
| 4. 数据库 | **SQLite 3.50.2, WAL 模式, FTS5 启用**, 单文件 `news-data/database/news.db`, 管道写/服务读共享 |

## 五~十三、数据事实（问题 5-13）

| 项 | 实测 |
|---|---|
| 5. Cron | ✅ 正常: `*/10 run`+`35* cleanup`+每日 backup/doctor; **06:10/06:20/06:30 三个槽位现场验证全链自动成功**（cron.log JSON 完整） |
| 6. 数据源数 | **52 个启用**（49 seed + 3 个早期遗留源） |
| 7. 源类型 | rss ×41 · sitemap ×3 · api ×3（HN Algolia×2, Bilibili）· gnews ×4（world/zh/reuters-site/business）· RSSHub **0**（主动弃用）· Crawl4AI **0**（主机不可行, 设计为默认关）· 普通网页/Scrapling 主链提取 **0 直采**（Scrapling 仅作提取兜底） |
| 8. 24h 抓到文章 | **1,308 篇**（6h 内增量: gnews-business 64, yahoo-finance 63, nyt-sitemap 60, gnews-zh 51…） |
| 9. 24h Story | 新建 **505**, 更新 **701**; 多源故事: 最大 21篇/14源（West Bank 事件）、14篇/9源（美伊油轮）、12篇/9源（Bombardier） |
| 10. 视频数据 | **60 篇**全元数据（YouTube×30 AJ/BBC/DW 频道, B站热门 20, Vimeo 10）; 无媒体文件落地 |
| 11. 图片 | **30 张本地**（2.75MB）+ 10 条失败标记（URL 元数据保留） |
| 12. 失败任务 | 任务状态: done 139 / pending 1119（积压=未处理, 非失败）/ **failed 0**; 图片下载失败 10（已落 crawl_errors, 标记行防重试风暴） |
| 13. 错误码分布 | 管道错误记录: HTTP 404 ×3（旧, YouTube 间歇）+ api adapter ×3（旧, 修复前）+ image ×10; **API 面（web.log 实测统计）: 200×359, 401×13, 429×262（压测+爬虫触发, 限速器正常工作）, 5xx ×0, timeout ×0, 404×1** |

## 十四~十七、磁盘（问题 14-17）

| 项 | 实测 |
|---|---|
| 14. 数据库 | 4.7MB（news.db）+ WAL ≤4.2MB（**已加 checkpoint(TRUNCATE), 单测 4.2MB→0**）; 索引/FTS 在内 |
| 15. 图片 | 2.9MB（30 张, 72h 滚动） |
| 16. 缓存 | 5.1MB / 85 个 gz（24h 原始页） |
| 17. inode | 全家 ~9,711 个文件（venv 38MB+node_modules 30MB 为大头）; 磁盘 139MB / 3GB 配额 = **4.6%** |

## 十八~二十、清理与恢复（问题 18-20）

| 项 | 实测 |
|---|---|
| 18. 72h 清理真正执行? | ✅: cleanup 实跑（`content_purged: 1`——当前全部数据 <24h, 可清理量本来就小）; purge_raw_cache/purge_images/archive_stories 逻辑就位 |
| 19. 是否符合预期? | **符合**（不删库, 只过期正文/图片/缓存; 元数据+Story+tags 永留）; *注意: 完整 72h 生命周期需系统运行满 72h 后复验*（本审计当日数据尚新） |
| 20. 重启自动恢复 | ✅ 实测 3 次 kill→下一个请求 200（Passenger 按需重生）; 管道 crash 由 cron 下槽重入 + 任务队列断点 |

## 附: 本审计当日发现并已修复（详见 PRODUCTION_AUDIT.md）
调度饥饿（P0 饿死 P2）、视频被类别门排除聚类、LIKE 兜底失效、单锚点误聚、limit=-5 绕过分页、cleanup 无 meta、WAL 无 checkpoint、图片失败不落日志。

---

# 2026-09-09 v2 增补（Global Intelligence 升级后）

- MCP: **12 工具**（+web_search/read_url/search_intelligence/deep_search）, Bearer/Origin/限速/日志脱敏不变
- Web Search: 5 keyless provider 上线（ddg/bing/gnews/bingnews/wikipedia）, SearXNG 可插拔 PRIMARY 就绪; 实测英文+中文查询返回真实结果, provider 级降级可观测
- URL Reader: trafilatura→Scrapling 子进程（并发≤2）; Guardian 实测 3978 字符/2.0s; inaccessible/needs_js 状态语义
- REST: + /api/search（scope=web|intelligence|all）/ /api/media; /api/status 暴露 MCP 真实状态/搜索配置/组件磁盘
- UI: 重定位为 Intelligence Console（Overview/Search/Events/Sources/Media/System）; Search 三 scope; 全部真实数据
- deep_search: web→读页→库关联, 2.3s 实测（无 AI）

---

# 2026-09-09 第三次增补（第二阶段产品化后）

- **认证**: admin/user 两级（服务端强制）; scrypt+盐; 会话 HttpOnly/Secure/SameSite; 登录限速; CSRF 头; auth.db 独立
- **MCP Token**: 具名多 Token（哈希入库/一次显示/撤销/调用统计）; env bootstrap 兼容
- **管理后台**: 14 页（MCP 服务/用户/来源管理/日志/诊断/设置/AI 状态）; 全部真实数据
- **UI**: 全中文界面（内容保持原文）; 搜索五范围; 事件为核心对象
- **SSRF**: read_url 7/7 内网目标拦截; Content-Type/大小/超时护栏
- **诊断**: 16/16 通过; MCP 自测 9/9; Token 生命周期闭环实测
- 管理员: admin（初始密码一次性交付, admin-credentials.txt 600）
